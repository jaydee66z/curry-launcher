"""Bounded, single-peer UDP offline negotiation, with explicit progress states."""

from dataclasses import dataclass
from enum import StrEnum
import math
import secrets
import socket
import time
from typing import Callable

from .protocol import (
    IncompatibleVersion, ProtocolError, Reply1, Reply2,
    check_mtu, check_protocol, decode, encode_request1, encode_request2,
)


class State(StrEnum):
    IDLE = "idle"
    REQUEST_1_SENT = "request_1_sent"
    REQUEST_2_SENT = "request_2_sent"
    OFFLINE_NEGOTIATED = "offline_negotiated"
    FAILED = "failed"


@dataclass(frozen=True)
class Negotiation:
    endpoint: tuple[str, int]
    server_guid: int
    client_guid: int
    observed_client_address: tuple[str, int]
    mtu: int
    elapsed_ms: float
    state: State = State.OFFLINE_NEGOTIATED


class OfflineClient:
    """No connected handshake, reliability layer, login, or replication yet.

    A fresh socket and GUID are used per attempt. Exactly two packets are sent
    on success, with no retries or background reconnects.
    """

    def __init__(self, *, protocol: int, mtu: int = 1200, timeout: float = 2.0,
                 on_state: Callable[[State], None] | None = None):
        self.protocol = check_protocol(protocol)
        self.mtu = check_mtu(mtu)
        if not math.isfinite(timeout) or not 0 < timeout <= 10:
            raise ValueError("Timeout must be finite and in (0, 10] seconds per exchange")
        self.timeout = timeout
        self.on_state = on_state
        self.state = State.IDLE

    def _transition(self, state: State) -> None:
        self.state = state
        if self.on_state:
            self.on_state(state)

    def _exchange(self, sock: socket.socket, request: bytes, state: State,
                  expected: type) -> Reply1 | Reply2:
        sock.send(request)
        self._transition(state)
        try:
            data = sock.recv(65535)
        except TimeoutError:
            raise TimeoutError(f"No reply after {self.timeout:g}s in state {state}") from None
        packet = decode(data)
        if isinstance(packet, IncompatibleVersion):
            raise ProtocolError(f"Peer rejected protocol {self.protocol}; advertises {packet.protocol}")
        if not isinstance(packet, expected):
            raise ProtocolError(f"Expected {expected.__name__}, received {type(packet).__name__}")
        return packet

    def negotiate(self, host: str, port: int) -> Negotiation:
        self._transition(State.IDLE)
        try:
            if not 1 <= port <= 65535:
                raise ValueError("Destination port must be 1..65535")
            # Numeric IPv4 endpoints make resolution explicit and avoid an
            # unbounded DNS call outside the exchange timeouts.
            socket.inet_pton(socket.AF_INET, host)
            endpoint = (host, port)
            guid = secrets.randbits(64)
            started = time.monotonic()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                # UDP connect filters incoming datagrams to this one peer.
                sock.connect(endpoint)
                reply1 = self._exchange(sock, encode_request1(self.protocol, self.mtu), State.REQUEST_1_SENT, Reply1)
                if reply1.mtu > self.mtu:
                    raise ProtocolError("Peer increased the requested MTU")
                reply2 = self._exchange(sock, encode_request2(endpoint, reply1.mtu, guid), State.REQUEST_2_SENT, Reply2)
                if reply2.server_guid != reply1.server_guid:
                    raise ProtocolError("Server GUID changed during negotiation")
                if reply2.mtu > reply1.mtu:
                    raise ProtocolError("Peer increased the negotiated MTU")
            self._transition(State.OFFLINE_NEGOTIATED)
            return Negotiation(endpoint, reply2.server_guid, guid, reply2.client_address,
                               reply2.mtu, round((time.monotonic() - started) * 1000, 3))
        except Exception:
            self._transition(State.FAILED)
            raise


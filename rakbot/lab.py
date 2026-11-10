"""Small local fixture, not a Roblox server or a full RakNet server."""

from concurrent.futures import ThreadPoolExecutor
import socket

from .client import Negotiation, OfflineClient
from .protocol import (
    ProtocolError, Request1, Request2, decode, encode_reply1, encode_reply2,
)


DEMO_PROTOCOL = 11  # Arbitrary lab setting; NOT a claimed Roblox version.
DEMO_GUID = 0x0102030405060708


def serve_once(sock: socket.socket) -> None:
    sock.settimeout(2)
    data, peer = sock.recvfrom(65535)
    first = decode(data)
    if not isinstance(first, Request1) or first.protocol != DEMO_PROTOCOL:
        raise ProtocolError("Lab expected OpenConnectionRequest1 with its demo version")
    mtu = min(first.mtu, 1200)
    sock.sendto(encode_reply1(DEMO_GUID, mtu), peer)
    data, second_peer = sock.recvfrom(65535)
    second = decode(data)
    if second_peer != peer or not isinstance(second, Request2):
        raise ProtocolError("Lab expected OpenConnectionRequest2 from the same peer")
    if second.mtu != mtu or second.server_address != sock.getsockname():
        raise ProtocolError("Request2 did not preserve the negotiated endpoint and MTU")
    sock.sendto(encode_reply2(DEMO_GUID, peer, mtu), peer)


def run_demo() -> Negotiation:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(serve_once, server)
            try:
                result = OfflineClient(protocol=DEMO_PROTOCOL).negotiate(*server.getsockname())
            finally:
                # Propagate fixture failures instead of silently losing them.
                future.result(timeout=3)
    return result


"""Two-step offline open recovered from native 0.744 and validated live.

This module authenticates session keys; application login lives above it.
"""

import base64
from dataclasses import dataclass, field
import json
import secrets
import socket
import struct
from urllib.parse import unquote_plus

from .bootstrap import ConnectionInfo
from .native_crypto import ClientKeyPair, CryptoError, EarlyCipher, SessionCipher
from .protocol import MAGIC, encode_address


# Unconditional bits in native 0.744's capability builder (0x102e26109).
# Runtime feature-flag bits remain unmapped; this is a minimal candidate mask.
BASE_CAPABILITIES = 0x2C350B30892


@dataclass(frozen=True, repr=False)
class OpenTicket:
    """Server-issued Request2 token segments, parsed like native setTicket."""
    header_token: bytes = field(repr=False)
    body_token: bytes = field(repr=False)
    hint: int

    @classmethod
    def parse(cls, ticket: str):
        try:
            if not isinstance(ticket, str) or not 0 < len(ticket) <= 8192:
                raise ValueError
            parts = ticket.split(";")
            if len(parts) < 5:
                raise ValueError
            header = base64.b64decode(parts[2], validate=True)
            body = base64.b64decode(parts[3], validate=True)
            hint = int(parts[-1], 10)
            if len(header) not in (32, 33, 50) or not 0 < len(body) <= 255 or not 0 <= hint <= 255:
                raise ValueError
        except (ValueError, TypeError):
            raise CryptoError("Client ticket does not contain supported Request2 tokens.") from None
        return cls(header, body, hint)

    def __repr__(self):
        return "OpenTicket(<redacted>)"


def rupp_token_prefix(token: bytes, destination: tuple[str, int] | None = None, *, kind: int = 1) -> bytes:
    if len(token) != 16:
        raise CryptoError("Initial RUPP token must be 16 bytes.")
    # v1, flags=0; TokenTlv type=1, len=17,
    # token kind=1, followed by the API-provided token.
    if kind not in (1, 2):
        raise CryptoError("Unsupported RUPP token kind.")
    fields = b"\x01\x11" + bytes([kind]) + token
    if destination is not None:
        host, port = destination
        try:
            address = socket.inet_pton(socket.AF_INET, host)
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError
        except (OSError, TypeError, ValueError):
            raise CryptoError("RUPP destination must be an IPv4 endpoint.") from None
        # Native Ipv4Tlv: type 2, six payload bytes; no RakNet IP inversion.
        fields += b"\x02\x06" + address + struct.pack(">H", port)
    return b"\x01\0" + struct.pack(">H", 4 + len(fields)) + fields


def strip_rupp(packet: bytes) -> tuple[bytes, int]:
    if len(packet) < 4 or packet[0] not in (1, 4):
        raise CryptoError("Unrecognized RUPP version.")
    size = int.from_bytes(packet[2:4], "big")
    if not 4 <= size <= len(packet):
        raise CryptoError("Invalid RUPP header size.")
    cursor = 4
    while cursor < size:
        if cursor + 2 > size:
            raise CryptoError("Truncated RUPP TLV.")
        length = packet[cursor + 1]
        cursor += 2 + length
        if cursor > size:
            raise CryptoError("RUPP TLV exceeds header size.")
    return packet[size:], size


class NativeOpen:
    def __init__(self, server_public: bytes, token: bytes | None, *, key_version: int = 5,
                 destination: tuple[str, int] | None = None, ticket: OpenTicket | None = None,
                 via_udmux: bool = True):
        if key_version != 5:
            raise CryptoError("This native candidate is only mapped for key version 5.")
        if type(via_udmux) is not bool:
            raise CryptoError("Endpoint transport must be explicitly UDMUX or direct.")
        if via_udmux and not isinstance(token, bytes):
            raise CryptoError("UDMUX requires its server-issued routing token.")
        self._pair = ClientKeyPair.generate()
        self._cipher = EarlyCipher(self._pair.client_keys(server_public))
        self._via_udmux = via_udmux
        self._prefix = rupp_token_prefix(token, destination) if via_udmux else b""
        self._destination = destination
        self._version = key_version
        self._guid = secrets.randbits(64)
        self._ticket = ticket
        self._route_updates = 0
        self._capabilities = BASE_CAPABILITIES

    def enable_shared_cache(self):
        from .shared_cache import CAPABILITY
        self._capabilities |= CAPABILITY

    @classmethod
    def from_connection(cls, info: ConnectionInfo):
        try:
            ephemeral = info._join_script.get("EphemeralEarlyPubKey", "")
            if not isinstance(ephemeral, str):
                raise ValueError
            if ephemeral:
                # Native PlayerConfigurer URL-decodes this field, then replaces
                # the RakNetEarlyPublicKey registry with its version-5 value.
                public = base64.b64decode(unquote_plus(ephemeral, errors="strict"), validate=True)
                version = 5
            else:
                app = json.loads(info._join_script["ClientPublicKeyData"])["applications"]["RakNetEarlyPublicKey"]
                version = app["send"]
                if type(version) is not int or version != 5:
                    raise ValueError
                row = next(row for row in app["versions"] if row["id"] == version and row.get("allowed") is True)
                public = base64.b64decode(row["value"], validate=True)
            if len(public) != 32:
                raise ValueError
            via_udmux = getattr(info, "via_udmux", True)
            token = base64.b64decode(info._join_script["TokenValue"], validate=True) if via_udmux else None
            destination = ((info._join_script["MachineAddress"], info._join_script["ServerPort"])
                           if via_udmux else None)
            ticket = OpenTicket.parse(info._join_script["ClientTicket"])
        except (ValueError, TypeError, KeyError, StopIteration):
            raise CryptoError("Connection info does not contain the mapped v5 key/token metadata.") from None
        return cls(public, token, key_version=version, destination=destination, ticket=ticket,
                   via_udmux=via_udmux)

    def unwrap(self, packet: bytes) -> tuple[bytes, int]:
        """Proxy headers belong only to UDMUX; direct ciphertext stays untouched."""
        return strip_rupp(packet) if self._via_udmux else (packet, 0)

    def accept_route_update(self, packet, prefix_size):
        """Apply a routing token only after the enclosing data authenticates."""
        if not self._via_udmux or not prefix_size:
            return
        _, checked_size = strip_rupp(packet)
        if checked_size != prefix_size:
            raise CryptoError('Unexpected routing header boundary.')
        cursor = 4
        while cursor < prefix_size:
            field_type, size = packet[cursor:cursor + 2]
            if field_type == 1 and size == 17 and packet[cursor + 2] == 2:
                prefix = rupp_token_prefix(packet[cursor + 3:cursor + 19], self._destination, kind=2)
                if prefix != self._prefix:
                    self._prefix = prefix
                    self._route_updates += 1
            cursor += 2 + size

    def decrypt_session(self, packet):
        payload, prefix_size = self.unwrap(packet)
        previous = self._session_cipher._receive_counter
        plain = self._session_cipher.decrypt(payload)
        # Delayed authenticated packets must not restore an older route token.
        current = self._session_cipher._receive_counter
        hint = int.from_bytes(payload[-18:-16], 'little')
        if current >= previous and (current & 65535) == hint:
            self.accept_route_update(packet, prefix_size)
        return plain

    def request(self, endpoint: tuple[str, int], *, mtu: int = 1200) -> bytes:
        """RbxOpenRequest2, sent only after an accepted RbxOpenReply1."""
        if not 576 <= mtu <= 1492:
            raise CryptoError("Candidate MTU must be 576..1492.")
        # Minimal native optional-field variant: capability mask, local
        # GUID, MTU, cipher proposal 1,
        # remote IPv4 address, and the server-issued body token.
        header_token = self._ticket.header_token if self._ticket else b""
        body_token = self._ticket.body_token if self._ticket else b""
        hint = self._ticket.hint if self._ticket else 0
        body = (struct.pack(">QQHB", self._capabilities, self._guid, mtu, 1) +
                encode_address(endpoint) + bytes([len(body_token)]) + body_token)
        header_size = 57 + len(header_token)
        header = (b"\x78" + MAGIC + bytes([3, header_size]) +
                  struct.pack(">HH", len(body), self._version) + self._pair.public +
                  bytes([hint, len(header_token)]) + header_token)
        if len(header) != header_size:
            raise AssertionError("Native header layout drifted")
        packet = self._prefix + self._cipher.encrypt(body, header)
        return packet.ljust(mtu - 40, b"\0")

    def request1(self, *, mtu: int = 1200) -> bytes:
        """Native 0x102e3ab0e: ID 0x7b, magic and constant trailer 0x05/0x01."""
        if not 576 <= mtu <= 1492:
            raise CryptoError("Candidate MTU must be 576..1492.")
        return (self._prefix + b"\x7b" + MAGIC + b"\x05\x01").ljust(mtu - 40, b"\0")

    @staticmethod
    def inspect_reply1(packet: bytes) -> dict:
        prefix_size = 0
        if packet[:1] in (b"\x01", b"\x04"):
            packet, prefix_size = strip_rupp(packet)
        result = {"kind": "unverified_response", "authenticated": False,
                  "rupp_header_bytes": prefix_size, "packet_id": packet[0] if packet else None}
        # Native processRbxOpenReply1 requires exactly 28 payload bytes.
        if len(packet) == 28 and packet[:17] == b"\x7e" + MAGIC:
            mtu = int.from_bytes(packet[26:28], "big")
            if 576 <= mtu <= 1492:
                result.update(kind="rbx_open_reply1", mtu=mtu)
        return result

    def inspect_reply(self, packet: bytes) -> dict:
        payload, prefix_size = self.unwrap(packet)
        result = {"bytes": len(packet), "rupp_header_bytes": prefix_size,
                  "packet_id": payload[0] if payload else None,
                  "authenticated": False}
        if len(payload) < 21 or payload[1:17] != MAGIC:
            return result
        header_bytes = payload[18]
        body_bytes = int.from_bytes(payload[19:21], "big")
        result["stage"] = payload[17]
        result["claimed_header_bytes"] = header_bytes
        result["claimed_body_bytes"] = body_bytes
        if payload[0] != 0x7d or not 21 <= header_bytes <= len(payload) - 28:
            return result
        # Reply2's native builder includes the RUPP size in its AAD length
        # and appends 28 reserved bytes before the actual AEAD trailer. Thus
        # body_bytes is not the encrypted byte count; authenticate the complete
        # received payload, then parse the reconstructed plaintext structure.
        plaintext = self._cipher.decrypt(payload, aad_bytes=header_bytes)
        decoded = payload[:header_bytes] + plaintext
        if body_bytes < 58 or len(decoded) < 79:
            raise CryptoError("Authenticated Reply2 has truncated session fields.")
        self._established_keys = self._pair.client_keys(decoded[21:53])
        self._server_guid = int.from_bytes(decoded[61:69], "big")
        self._negotiated_capabilities = int.from_bytes(decoded[53:61], "big")
        self._format = decoded[71]
        self._mtu = int.from_bytes(decoded[69:71], "big")
        if not 576 <= self._mtu <= 1492:
            raise CryptoError("Authenticated Reply2 has unsupported MTU.")
        self._session_cipher = SessionCipher(self._established_keys, self._format)
        self.accept_route_update(packet, prefix_size)
        result["authenticated"] = True
        result["plaintext_bytes"] = len(plaintext)
        result.update(kind="rbx_open_reply2", offline_open=True, mtu=self._mtu,
                      cipher_format=self._format)
        return result

    def __repr__(self):
        return "NativeOpen(<session data redacted>)"


def attempt_native_open(info: ConnectionInfo, *, timeout: float = 3) -> dict:
    """At most two packets, one bounded window per stage. No game session."""
    if not 0 < timeout <= 5:
        raise CryptoError("Open timeout must be in (0, 5].")
    endpoint = info.endpoints[0]
    candidate = NativeOpen.from_connection(info)
    request = candidate.request1()
    stages = []
    sent_bytes = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect(endpoint)
        sock.send(request)
        sent_bytes += len(request)
        try:
            packet = sock.recv(65535)
            reply = candidate.inspect_reply1(packet)
            stages.append({"stage": "request1", "reply": reply})
            if reply["kind"] == "rbx_open_reply1":
                request = candidate.request(endpoint, mtu=reply["mtu"])
                sock.send(request)
                sent_bytes += len(request)
                packet = sock.recv(65535)
                reply = candidate.inspect_reply(packet)
                stages.append({"stage": "request2", "reply": reply})
        except TimeoutError:
            reply = {"kind": "timeout", "authenticated": False}
        except CryptoError as error:
            reply = {"kind": "unverified_response", "authenticated": False,
                     "reason": str(error), "bytes": len(packet),
                     "first_byte": packet[0] if packet else None}
    if not stages or stages[-1]["reply"] is not reply:
        stages.append({"stage": "request2" if len(stages) else "request1", "reply": reply})
    return {"state": "native_offline_open_authenticated" if reply.get("offline_open") else "native_open_failed", "sent_bytes": sent_bytes,
            "stages": stages, "reply": reply, "game_session": False,
            "note": "Offline session keys only; use connect for the connected transport. No player spawn."}

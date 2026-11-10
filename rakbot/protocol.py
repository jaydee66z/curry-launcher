"""IPv4, unsecured RakNet offline negotiation.

Wire layout reference: facebookarchive/RakNet, Source/RakPeer.cpp.
This module deliberately makes no claim about current Roblox compatibility.
"""

from dataclasses import dataclass
from enum import IntEnum
from ipaddress import IPv4Address
import struct


MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")
IP_UDP_OVERHEAD = 28
MIN_MTU = 576
MAX_MTU = 1492


class ProtocolError(ValueError):
    """Malformed, unexpected, or unsupported wire data."""


class UnsupportedSecurity(ProtocolError):
    """The peer requires a security variant this prototype cannot handle."""


class PacketID(IntEnum):
    OPEN_REQUEST_1 = 0x05
    OPEN_REPLY_1 = 0x06
    OPEN_REQUEST_2 = 0x07
    OPEN_REPLY_2 = 0x08
    INCOMPATIBLE_VERSION = 0x19


@dataclass(frozen=True)
class Request1:
    protocol: int
    mtu: int


@dataclass(frozen=True)
class Reply1:
    server_guid: int
    mtu: int


@dataclass(frozen=True)
class Request2:
    server_address: tuple[str, int]
    mtu: int
    client_guid: int


@dataclass(frozen=True)
class Reply2:
    server_guid: int
    client_address: tuple[str, int]
    mtu: int


@dataclass(frozen=True)
class IncompatibleVersion:
    protocol: int
    server_guid: int


def check_mtu(mtu: int) -> int:
    if not MIN_MTU <= mtu <= MAX_MTU:
        raise ProtocolError(f"MTU must be {MIN_MTU}..{MAX_MTU}; got {mtu}")
    return mtu


def check_protocol(protocol: int) -> int:
    if not 0 <= protocol <= 255:
        raise ProtocolError("Protocol version must fit in one byte")
    return protocol


def _guid(guid: int) -> bytes:
    if not 0 <= guid < 2**64:
        raise ProtocolError("GUID must fit in an unsigned 64-bit integer")
    return struct.pack(">Q", guid)


def _header(packet_id: PacketID) -> bytes:
    return bytes([packet_id]) + MAGIC


def encode_address(address: tuple[str, int]) -> bytes:
    host, port = address
    if not 0 <= port <= 65535:
        raise ProtocolError("Port must be 0..65535")
    # RakNet's IPv4 SystemAddress inverts the four address octets.
    octets = IPv4Address(host).packed
    return b"\x04" + bytes(value ^ 0xFF for value in octets) + struct.pack(">H", port)


def decode_address(data: bytes) -> tuple[str, int]:
    if len(data) != 7:
        raise ProtocolError("IPv4 SystemAddress must be exactly 7 bytes")
    if data[0] != 4:
        raise ProtocolError(f"Unsupported address family: {data[0]}")
    return str(IPv4Address(bytes(value ^ 0xFF for value in data[1:5]))), int.from_bytes(data[5:7], "big")


def encode_request1(protocol: int, mtu: int) -> bytes:
    header = _header(PacketID.OPEN_REQUEST_1) + bytes([check_protocol(protocol)])
    # MTU includes the IPv4 and UDP headers, not just this payload.
    return header.ljust(check_mtu(mtu) - IP_UDP_OVERHEAD, b"\0")


def encode_reply1(server_guid: int, mtu: int) -> bytes:
    return _header(PacketID.OPEN_REPLY_1) + _guid(server_guid) + b"\0" + struct.pack(">H", check_mtu(mtu))


def encode_request2(address: tuple[str, int], mtu: int, client_guid: int) -> bytes:
    return _header(PacketID.OPEN_REQUEST_2) + encode_address(address) + struct.pack(">H", check_mtu(mtu)) + _guid(client_guid)


def encode_reply2(server_guid: int, address: tuple[str, int], mtu: int) -> bytes:
    return _header(PacketID.OPEN_REPLY_2) + _guid(server_guid) + encode_address(address) + struct.pack(">H", check_mtu(mtu)) + b"\0"


def encode_incompatible(protocol: int, server_guid: int) -> bytes:
    return bytes([PacketID.INCOMPATIBLE_VERSION, check_protocol(protocol)]) + MAGIC + _guid(server_guid)


def _length(data: bytes, expected: int) -> None:
    if len(data) != expected:
        raise ProtocolError(f"Packet 0x{data[0]:02x}: expected {expected} bytes, got {len(data)}")


def decode(data: bytes) -> Request1 | Reply1 | Request2 | Reply2 | IncompatibleVersion:
    if not data:
        raise ProtocolError("Empty datagram")
    try:
        packet_id = PacketID(data[0])
    except ValueError:
        raise ProtocolError(f"Unsupported packet ID 0x{data[0]:02x}; not an implemented offline RakNet packet") from None

    magic_offset = 2 if packet_id == PacketID.INCOMPATIBLE_VERSION else 1
    if data[magic_offset:magic_offset + 16] != MAGIC:
        raise ProtocolError("Missing or invalid offline RakNet magic")

    if packet_id == PacketID.OPEN_REQUEST_1:
        mtu = check_mtu(len(data) + IP_UDP_OVERHEAD)
        return Request1(data[17], mtu)
    if packet_id == PacketID.OPEN_REPLY_1:
        if len(data) < 26:
            raise ProtocolError("Truncated OpenConnectionReply1")
        if data[25]:
            raise UnsupportedSecurity("Secured OpenConnectionReply1 is not implemented")
        _length(data, 28)
        return Reply1(int.from_bytes(data[17:25], "big"), check_mtu(int.from_bytes(data[26:28], "big")))
    if packet_id == PacketID.OPEN_REQUEST_2:
        _length(data, 34)
        return Request2(decode_address(data[17:24]), check_mtu(int.from_bytes(data[24:26], "big")), int.from_bytes(data[26:34], "big"))
    if packet_id == PacketID.OPEN_REPLY_2:
        if len(data) < 35:
            raise ProtocolError("Truncated OpenConnectionReply2")
        # RakNet writes this flag as one bit, at the MSB of the final byte.
        if data[34] & 0x80:
            raise UnsupportedSecurity("Secured OpenConnectionReply2 is not implemented")
        _length(data, 35)
        if data[34] != 0:
            raise ProtocolError("Unexpected padding bits in OpenConnectionReply2")
        return Reply2(int.from_bytes(data[17:25], "big"), decode_address(data[25:32]), check_mtu(int.from_bytes(data[32:34], "big")))
    _length(data, 26)
    return IncompatibleVersion(data[1], int.from_bytes(data[18:26], "big"))


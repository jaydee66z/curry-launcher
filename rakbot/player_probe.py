"""Identify a Player record at the start of a Data packet, without executing it.

Partial native NewInstance reader (0x105809fa2 / 0x105808a78). This does not
read the remaining Data items, build a world or establish a character spawn.
"""

import struct

from .native_crypto import CryptoError
from .schema import Reader
from .application import varuint


def request_character(wire_guid, spawn_name=""):
    """Native RequestCharacterItem writer 0x105713118, unmapped Data IDs.

    Empty local error report, LE32-length spawn name, existing Player GUID.
    Sending this alone does not establish server acceptance or avatar spawn.
    """
    if (not isinstance(wire_guid, tuple) or len(wire_guid) != 2 or
            any(type(value) is not int for value in wire_guid) or
            not 1 <= wire_guid[0] <= 0xffffffff or not 0 <= wire_guid[1] <= 0xffffffff or
            not isinstance(spawn_name, str)):
        raise CryptoError("Invalid character request fields.")
    try:
        encoded = spawn_name.encode("utf-8")
    except UnicodeError:
        raise CryptoError("Invalid character request name encoding.") from None
    if len(encoded) > 8192:
        raise CryptoError("Character request name exceeds its bound.")
    return (b"\x83\x08" + struct.pack("<II", 0, len(encoded)) + encoded +
            varuint(wire_guid[0]) + struct.pack("<I", wire_guid[1]) + b"\0")


def marker_ack(packet):
    """Native Marker job 0x105804546: Data item 4 + raw LE32, then end item 0."""
    if len(packet) != 5 or packet[0] != 0x84:
        raise CryptoError("Unsupported replication marker layout.")
    return b"\x83\x04" + packet[1:] + b"\x00"


def initial_player_record(packet, schema, account_id):
    if len(packet) < 9 or packet[:2] != b"\x83\x02":
        return None
    reader = Reader(packet)
    reader.take(2)
    try:
        # GUID: unsigned scope varint followed by LE32 object index.
        scope = reader.var(2**32 - 1)
        if scope == 0:
            return None
        object_index = reader.u32()
        class_id = reader.u16()
        if class_id >= len(schema.classes):
            return None
        descriptor = schema.classes[class_id]
        if descriptor["name"] != "Player":
            return None
        # Native NewInstance has two lists of class-relative property IDs.
        # Each list ends at ff. Read explicit IDs, never search for account bytes.
        for _ in range(2):
            previous = -1
            while True:
                index = reader.take(1)[0]
                if index == 255:
                    break
                if index <= previous or index >= len(descriptor["properties"]):
                    return None
                previous = index
                prop = descriptor["properties"][index]
                value = _value(reader, prop["type"])
                if prop["name"] == "UserId" and prop["type"] == 44:
                    return {"account_matches": value == account_id,
                            "consumed_bytes": reader.at, "complete_packet": False,
                            "wire_guid": (scope, object_index)}
    except CryptoError:
        # The full Data reader is not implemented; unsupported layouts cannot
        # establish a Player record, but may still be valid server packets.
        return None
    return None


def _value(reader, kind):
    if kind in (2, 8):
        return reader.take(reader.var(1048576))
    if kind in (7, 10, 44):
        value = reader.var(2**64 - 1 if kind == 44 else 2**32 - 1)
        return (value >> 1) ^ -(value & 1) if kind in (10, 44) else value
    if kind == 9:
        return reader.take(1)[0] != 0
    if kind == 11:
        return struct.unpack("<f", reader.take(4))[0]
    if kind == 22:
        return struct.unpack("<fff", reader.take(12))
    if kind == 18:
        return reader.u16()
    if kind == 28:
        scope = reader.var(2**32 - 1)
        return None if scope == 0 else (scope, reader.u32())
    if kind == 55:
        return int.from_bytes(reader.take(8), "little")
    if kind == 49:
        size = reader.take(1)[0]
        if size & 128:
            raise CryptoError("Cached property names require the full Data reader.")
        if size == 127:
            size = reader.var(8192)
        return reader.take(size)
    if kind == 68:
        # Native 0x1059e9222: signed64, domain enum, two signed64 fields.
        # Only domain 1 has been observed and checked in this investigation.
        first = reader.var(2**64 - 1)
        if reader.var(2**32 - 1) != 1:
            raise CryptoError("Unsupported User domain in Player probe.")
        return first, reader.var(2**64 - 1), reader.var(2**64 - 1)
    raise CryptoError("Unsupported Player property type in partial reader.")

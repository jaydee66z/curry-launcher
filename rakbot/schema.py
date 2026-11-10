"""Bounded reader for native 0.744 schema version 3 (0x1057ac06a).

This describes wire types; it does not instantiate or execute Roblox objects.
"""

from dataclasses import dataclass, field
import struct
import os

from .native_crypto import CryptoError


MAX_SCHEMA_BYTES = 4 * 1024 * 1024


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, size):
        if not 0 <= size <= len(self.data) - self.at:
            raise CryptoError("Truncated network schema.")
        value = self.data[self.at:self.at + size]
        self.at += size
        return value

    def skip(self, size):
        if not 0 <= size <= len(self.data) - self.at:
            raise CryptoError('Truncated network schema.')
        self.at += size

    def var(self, limit=65535):
        value = 0
        for shift in range(0, 70, 7):
            byte = self.u8()
            value |= (byte & 127) << shift
            if byte < 128:
                if value > limit:
                    break
                return value
        raise CryptoError("Network schema integer exceeds its bound.")

    def u8(self):
        if self.at >= len(self.data):
            raise CryptoError('Truncated network schema.')
        value = self.data[self.at]
        self.at += 1
        return value

    def text(self):
        try:
            return self.take(self.var(8192)).decode("utf-8")
        except UnicodeError:
            raise CryptoError("Unsupported network schema string encoding.") from None

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]


PythonReader = Reader
if os.environ.get('RAKBOT_PYTHON_READER') != '1':
    try:
        from ._reader import Reader
    except ImportError:
        pass  # Portable fallback when the optional stable-ABI module is absent.


@dataclass(repr=False)
class Schema:
    capabilities: int
    enums: list = field(repr=False)
    classes: list = field(repr=False)
    properties: list = field(repr=False)
    events: list = field(repr=False)
    string_tables: list = field(repr=False)
    isr: dict = field(repr=False)
    dynamic_types: list = field(repr=False)
    decoded_bytes: int

    def summary(self):
        return {"version": 3, "enums": len(self.enums), "classes": len(self.classes),
                "properties": len(self.properties), "events": len(self.events),
                "string_table_sizes": [len(table) for table in self.string_tables],
                "isr_classes": len(self.isr), "dynamic_type_rows": len(self.dynamic_types),
                "decoded_bytes": self.decoded_bytes, "complete": True}


def parse_schema(data):
    if not 1 <= len(data) <= MAX_SCHEMA_BYTES:
        raise CryptoError("Network schema size exceeds its bound.")
    reader = Reader(data)
    if reader.var() != 3:
        raise CryptoError("Unsupported network schema version.")
    capabilities = int.from_bytes(reader.take(8), "little")
    enums = [{"name": reader.text(), "bits": reader.take(1)[0]} for _ in range(reader.var())]
    class_count, property_count, event_count = reader.var(), reader.var(), reader.var()
    properties, events, classes = [], [], []

    def enum_index():
        index = reader.u16()
        if index != 65535 and index >= len(enums):
            raise CryptoError("Network schema enum index is out of range.")
        return index

    for class_id in range(class_count):
        entry = {"name": reader.text(), "properties": [], "events": []}
        count = reader.var(property_count - len(properties))
        for _ in range(count):
            prop = {"id": len(properties), "class_id": class_id,
                    "name": reader.text(), "type": reader.take(1)[0]}
            if prop["type"] == 7:
                prop["enum"] = enum_index()
            elif prop["type"] == 60:
                prop["dynamic_type"] = reader.var()
                if prop["dynamic_type"] == 65535:
                    raise CryptoError("Unsupported dynamic property type.")
            entry["properties"].append(prop)
            properties.append(prop)
        entry["wire_id"] = reader.u16()
        count = reader.var(event_count - len(events))
        for _ in range(count):
            event = {"id": len(events), "class_id": class_id,
                     "name": reader.text(), "arguments": []}
            for _ in range(reader.var(256)):
                event["arguments"].append({"type": reader.take(1)[0], "enum": enum_index()})
            entry["events"].append(event)
            events.append(event)
        classes.append(entry)
    if len(properties) != property_count or len(events) != event_count:
        raise CryptoError("Network schema member totals do not match.")

    # Optional trailing tables were added after the base schema format.
    tables, isr, dynamic = [], {}, []
    for _ in range(2):
        if reader.at < len(data):
            tables.append([reader.text() for _ in range(reader.var())])
    if reader.at < len(data):
        count = reader.u32()
        if count > class_count:
            raise CryptoError("Network schema ISR class count is out of range.")
        for _ in range(count):
            class_id, count = reader.u32(), reader.u32()
            if class_id >= class_count or class_id in isr or count > 128:
                raise CryptoError("Network schema ISR descriptor is out of range.")
            ids = [reader.u32() for _ in range(count)]
            if any(index >= property_count or properties[index]["class_id"] != class_id for index in ids):
                raise CryptoError("Network schema ISR property is out of range.")
            isr[class_id] = ids
    if reader.at < len(data):
        for _ in range(reader.var()):
            row = [reader.var(), reader.var(), reader.var()]
            if row[2]:
                row.append(reader.var())
            dynamic.append(row)
    if reader.at != len(data):
        raise CryptoError("Unexpected trailing network schema data.")
    return Schema(capabilities, enums, classes, properties, events, tables, isr, dynamic, len(data))


def decode_schema_packet(packet):
    # Native compressed block reader 0x10584c00e: LE32 compressed/plain sizes.
    if len(packet) < 9 or packet[0] != 0x97:
        raise CryptoError("Unsupported network schema packet.")
    compressed, expanded = struct.unpack_from("<II", packet, 1)
    if compressed != len(packet) - 9 or not 1 <= compressed <= MAX_SCHEMA_BYTES or not 1 <= expanded <= MAX_SCHEMA_BYTES:
        raise CryptoError("Network schema envelope size is invalid.")
    try:
        from compression import zstd
    except ImportError:
        raise CryptoError("Schema decoding requires Python 3.14 compression.zstd.") from None
    try:
        decoder = zstd.ZstdDecompressor()
        raw = decoder.decompress(packet[9:], max_length=expanded + 1)
        if len(raw) != expanded or not decoder.eof or decoder.unused_data:
            raise CryptoError("Network schema compressed stream size mismatch.")
    except zstd.ZstdError:
        raise CryptoError("Invalid compressed network schema.") from None
    return parse_schema(raw)

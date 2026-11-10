"""Inspect one captured 0x9b/RSB1 packet statically; never execute its bytecode.

Requires Python 3.14's compression.zstd and the official Luau headers under
.reverse-inputs/luau. Output contains counts/API names, not raw code or values.
"""

from collections import Counter
from pathlib import Path
import re
import struct

from .application_crypto import ticket_hash

ROOT = Path(__file__).resolve().parents[1]


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, count):
        if not 0 <= count <= len(self.data) - self.at:
            raise ValueError("Truncated bytecode structure")
        result = self.data[self.at:self.at + count]
        self.at += count
        return result

    def var(self):
        result = 0
        for shift in range(0, 35, 7):
            byte = self.take(1)[0]
            result |= (byte & 127) << shift
            if byte < 128:
                return result
        raise ValueError("Oversized bytecode integer")


def unpack_rsb(data):
    if not 12 <= len(data) <= 1048576:
        raise ValueError("Unsupported RSB size")
    key = bytes(((data[i] ^ b"RSB1"[i]) - i * 41) & 255 for i in range(4))
    plain = bytes(value ^ ((key[i % 4] + i * 41) & 255) for i, value in enumerate(data))
    if ticket_hash(plain, 42) != int.from_bytes(key, "little"):
        raise ValueError("RSB checksum mismatch")
    size = int.from_bytes(plain[4:8], "little")
    if not 0 < size <= 1048576:
        raise ValueError("RSB decompressed size exceeds limit")
    from compression import zstd
    decoder = zstd.ZstdDecompressor()
    raw = decoder.decompress(plain[8:], max_length=size + 1)
    if len(raw) != size or not decoder.eof or decoder.unused_data:
        raise ValueError("RSB size or zstd stream mismatch")
    return raw


def inspect(raw, headers, *, normalized=None):
    if normalized is not None and (not isinstance(normalized, bytearray) or len(normalized) != len(raw)):
        raise ValueError("Normalization buffer must match the validated input")
    reader = Reader(raw)
    version, types_version = reader.take(2)
    if version != 14 or types_version != 3:
        raise ValueError("Only observed Luau 14/type 3 is mapped")
    strings = [reader.take(reader.var()) for _ in range(reader.var())]
    while reader.take(1)[0]:
        reader.var()  # userdata mapping string index
    bytecode = (headers / "Bytecode.h").read_text(encoding="utf-8")
    enum = bytecode.split("enum LuauOpcode", 1)[1].split("};", 1)[0]
    names = re.findall(r"^\s*LOP_([A-Z][A-Z0-9_]*),", enum, re.M)
    utils = (headers / "BytecodeUtils.h").read_text(encoding="utf-8")
    lengths = utils.split("inline int getOpLength", 1)[1].split("return 2;", 1)[0]
    two_words = set(re.findall(r"case LOP_([A-Z][A-Z0-9_]*):", lengths))
    functions = []
    for index in range(reader.var()):
        size = reader.var()
        begin = reader.at
        if not 0 < size <= len(raw) - begin:
            raise ValueError("Invalid Luau function size")
        stack, params, upvalues, vararg, flags = reader.take(5)
        reader.take(reader.var())  # types
        count = reader.var()
        if count > (begin + size - reader.at) // 4:
            raise ValueError("Function instruction count exceeds its bounds")
        code_at = reader.at
        words = struct.unpack("<" + str(count) + "I", reader.take(count * 4))
        pc, opcodes = 0, Counter()
        while pc < count:
            opcode = ((words[pc] & 255) * 203) & 255
            if opcode >= len(names):
                raise ValueError("Unknown encoded Luau opcode")
            name = names[opcode]
            if normalized is not None:
                normalized[code_at + pc * 4] = opcode
            opcodes[name] += 1
            pc += 2 if name in two_words else 1
        if pc != count:
            raise ValueError("Truncated Luau auxiliary word")
        if reader.at > begin + size:
            raise ValueError("Function metadata exceeds its bounds")
        reader.at = begin + size
        functions.append({"index": index, "bytes": size, "stack": stack, "parameters": params,
                          "upvalues": upvalues, "words": count, "opcodes": dict(opcodes)})
    main = reader.var()
    if main >= len(functions):
        raise ValueError("Invalid main function index")
    # These are API names only; unknown strings/values are never emitted.
    allowed = "bit32 bor NextInteger getmetatable setmetatable UserSettings tostring os exit game RunService GetService IsStudio newproxy __namecall Random new __add __sub JobId byte xpcall".split()
    return {"version": version, "types_version": types_version, "string_count": len(strings),
            "known_apis": [name for name in allowed if name.encode() in strings],
            "functions": functions, "main_function": main, "trailer_bytes": len(raw) - reader.at}


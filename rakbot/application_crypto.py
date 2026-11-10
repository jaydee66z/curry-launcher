"""Recovered legacy application envelope; separate from UDP session AEAD."""

import secrets
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .native_crypto import CryptoError


def rolling_checksum(data):
    state, total = 0xd971, 0
    for byte in data:
        value = (state >> 8) ^ byte
        state = ((state + value) * 0xce6d + 0x58bf) & 65535
        total = (total + value) & 0xffffffff
    return total


def seal(message, key, *, random_byte=None):
    """Native 0x1057b32cc/0x1059d57b8: preserve ID, seal remaining bytes.

    Blocks are chained in native order: first, last, penultimate, ..., second.
    Fresh randomness is used in production; explicit bytes are for fixtures.
    """
    if not message or len(key) != 16 or len(message) > 32768:
        raise CryptoError("Unsupported application envelope size or key.")
    if b"\0" in key:
        raise CryptoError("Native application key must not contain a NUL byte.")
    if random_byte is None:
        random_byte = lambda: secrets.randbits(8)
    body = message[1:]
    padding = 15 - ((len(body) + 5) & 15)
    plain = bytearray(bytes(4) + bytes([random_byte(), ((random_byte() << 4) & 240) | padding]) +
                      bytes(random_byte() for _ in range(padding)) + body)
    plain[:4] = struct.pack("<I", rolling_checksum(plain[4:]))
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    previous = bytes(16)
    for offset in [0, *range(len(plain) - 16, 0, -16)]:
        block = bytes(a ^ b for a, b in zip(plain[offset:offset + 16], previous))
        previous = encryptor.update(block)
        plain[offset:offset + 16] = previous
    encryptor.finalize()
    return message[:1] + bytes(plain)


def rotate(value, bits):
    value &= 0xffffffff
    return ((value << bits) | (value >> (32 - bits))) & 0xffffffff


def ticket_hash(data, seed=1):
    """XXH32, matching native 0x1032f89d3 (not CRC32)."""
    mask = 0xffffffff
    p1, p2, p3, p4, p5 = 0x9e3779b1, 0x85ebca77, 0xc2b2ae3d, 0x27d4eb2f, 0x165667b1
    cursor = 0
    if len(data) >= 16:
        lanes = [(seed + p1 + p2) & mask, (seed + p2) & mask, seed & mask, (seed - p1) & mask]
        while cursor <= len(data) - 16:
            for n, word in enumerate(struct.unpack_from("<4I", data, cursor)):
                lanes[n] = rotate(lanes[n] + word * p2, 13) * p1 & mask
            cursor += 16
        result = sum(rotate(lanes[n], bits) for n, bits in enumerate((1, 7, 12, 18))) & mask
    else:
        result = (seed + p5) & mask
    result = (result + len(data)) & mask
    while cursor <= len(data) - 4:
        result = rotate(result + struct.unpack_from("<I", data, cursor)[0] * p3, 17) * p4 & mask
        cursor += 4
    for byte in data[cursor:]:
        result = rotate(result + byte * p5, 11) * p1 & mask
    result ^= result >> 15
    result = result * p2 & mask
    result ^= result >> 13
    result = result * p3 & mask
    return (result ^ (result >> 16)) & mask


def ticket_check(value):
    """Native 0x1056ebb9b, reduced for this build's fixed 0x752fab0b seed."""
    seed, sentinel = 0x752fab0b, 0x557bb5d7
    value = rotate((rotate(value + sentinel, 25) - sentinel) * seed, 13)
    value = rotate(sentinel ^ ((seed - value) & 0xffffffff), 15)
    value = rotate(value - seed - sentinel, 9)
    value = rotate(seed - value + sentinel, 3) ^ seed
    return -value & 0xffffffff

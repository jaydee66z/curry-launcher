"""Bounded A1 instance state reader, native 0.744 modes 0..3.

Class and property IDs come from the received schema. Unsupported property
payloads are skipped only at their explicit native LE16 length boundary.
"""
from collections import Counter
import struct

from .native_crypto import CryptoError
from .physics import read_pv, coordinates
from .application import varuint
from .schema import Reader


def guid(reader):
    scope = reader.var(2**32 - 1)
    return None if scope == 0 else (scope, reader.u32())


def decode(packet, schema):
    if not packet or packet[0] != 0xa1 or len(packet) > 4 * 1024 * 1024:
        raise CryptoError('Unsupported ISR packet envelope.')
    reader = Reader(packet)
    reader.take(1)
    frame, groups, acknowledgement = reader.u32(), reader.u32(), reader.u32()
    if groups > 4096:
        raise CryptoError('ISR group count exceeds bound.')
    updates, skipped, total = [], Counter(), 0
    for _ in range(groups):
        count, mode, age = reader.u16(), reader.take(1)[0], reader.take(1)[0]
        total += count
        if total > 16384 or mode > 3:
            raise CryptoError('ISR record count or mode exceeds bound.')
        for _ in range(count):
            key, cid = guid(reader), reader.u16()
            if key is None or cid >= len(schema.classes):
                raise CryptoError('Invalid ISR instance identity or class.')
            bits = reader.u16()
            if bits > 256:
                raise CryptoError('ISR property mask exceeds bound.')
            mask = int.from_bytes(reader.take(((bits + 63) // 64) * 8), 'little')
            if mask >> bits:
                raise CryptoError('ISR mask has bits outside declared size.')
            payload = Reader(reader.take(reader.u16()))
            props = schema.isr.get(cid)
            if props is None or bits > len(props):
                skipped['unsupported_class_or_mode'] += 1
                continue
            values = {}
            while mask:
                bit = mask & -mask
                index = bit.bit_length() - 1
                mask ^= bit
                prop = schema.properties[props[index]]
                kind = prop['type']
                if kind in (28, 69):
                    value = guid(payload)
                elif kind == 57:
                    value = read_pv(payload, mode)
                elif kind == 11:
                    value = struct.unpack('<f', payload.take(4))[0]
                elif kind == 22:
                    value = struct.unpack('<fff', payload.take(12))
                else:
                    skipped[f'property_type:{kind}'] += 1
                    break
                values[prop['name']] = value
            else:
                if payload.at != len(payload.data):
                    raise CryptoError('ISR property payload has trailing bytes.')
                updates.append((key, cid, (frame - age) & 0xffffffff, values))
    if reader.at != len(packet):
        raise CryptoError('ISR packet has trailing bytes.')
    return {'frame': frame, 'acknowledgement': acknowledgement,
            'updates': updates, 'skipped': skipped, 'records': total}


def stationary_packet(root, class_id, property_count, pv_index, position, frame, acknowledgement):
    """One own-root mode-0 ISR record; native headers 0x104cf9c7d.

    Encoding a record does not establish ownership or server acceptance.
    """
    if (not isinstance(root, tuple) or len(root) != 2 or
            any(type(v) is not int for v in (*root, class_id, property_count, pv_index, frame, acknowledgement)) or
            not 1 <= root[0] <= 0xffffffff or not 0 <= root[1] <= 0xffffffff or
            not 0 <= class_id <= 65535 or not 1 <= property_count <= 256 or
            not 0 <= pv_index < property_count or not 0 <= frame <= 0xffffffff or
            not 0 <= acknowledgement <= 0xffffffff):
        raise CryptoError('Unsupported outgoing ISR identity or header.')
    encoded_position = coordinates(position)
    pv = (b'\xe0' if all(v == 0 for v in position) else b'\x60' + encoded_position)
    pv += bytes.fromhex('0000000000c0')
    mask = (1 << pv_index).to_bytes(((property_count + 63) // 64) * 8, 'little')
    return (b'\xa1' + struct.pack('<IIIHBB', frame, 1, acknowledgement, 1, 0, 0) +
            varuint(root[0]) + struct.pack('<IH', root[1], class_id) +
            struct.pack('<H', property_count) + mask + struct.pack('<H', len(pv)) + pv)

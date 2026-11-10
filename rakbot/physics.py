"""Native 0.744 physics primitives, checked against synthetic native fixtures."""
import math
import struct

from .application import varuint
from .native_crypto import CryptoError


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def coordinates(position):
    if (len(position) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or
                                 abs(v) > 2**30 for v in position)):
        raise CryptoError('Position must contain three finite coordinates within the physics range.')
    values = [f32(v) for v in position]
    exponent = min(31, max(0, math.frexp(max(map(abs, values)))[1]))
    bits = 10 if exponent <= 4 else 16 if exponent <= 10 else 21
    scale, denominator = float(2**exponent), 2**bits - 1
    quantized = [math.trunc(f32(f32(f32(v / scale) * denominator) + (0.5 if v >= 0 else -0.5)))
                 for v in values]
    flags = exponent << 3
    for index, value in enumerate(quantized):
        flags |= ((value >> bits) & 1) << (2 - index)
    x, y, z = [v & denominator for v in quantized]
    if bits == 10:
        body = struct.pack('<I', x << 20 | y << 10 | z)
    elif bits == 16:
        body = struct.pack('<HHH', x, y, z)
    else:
        body = struct.pack('<II', x << 11 | y >> 10, (y << 21 | z) & 0xffffffff)
    return bytes([flags]) + body


def read_coordinates(reader):
    """Inverse native 0x10571e742, including its float32 rounding."""
    flags = reader.take(1)[0]
    exponent = flags >> 3
    bits = 10 if flags <= 0x27 else 16 if flags <= 0x57 else 21
    mask = (1 << bits) - 1
    if bits == 10:
        packed = reader.u32()
        values = [(packed >> 20) & mask, (packed >> 10) & mask, packed & mask]
    elif bits == 16:
        values = [reader.u16() for _ in range(3)]
    else:
        first, second = reader.u32(), reader.u32()
        values = [first >> 11, ((first & 0x7ff) << 10) | second >> 21, second & mask]
    signed = [v - (1 << bits) if flags & (1 << (2 - i)) else v for i, v in enumerate(values)]
    return tuple(f32(f32(float(v) / mask) * 2**exponent) for v in signed)


def read_pv(reader, mode=0):
    """Native ISR modes 0..3. Rotation is retained as opaque bytes."""
    if mode not in (0, 1, 2, 3):
        raise CryptoError('Unsupported ISR physics encoding mode.')
    flags = reader.take(1)[0]
    position = (0.0, 0.0, 0.0) if flags & 128 else read_coordinates(reader)
    rotation = flags & 31
    if rotation == 0:
        reader.take(4 if mode in (2, 3) else 6)
    elif rotation == 31:
        reader.take(28)  # native 0x1059e9f0e reads seven float32 values
    elif rotation > 24:
        raise CryptoError('Unsupported ISR rotation code.')
    for omitted in (64, 32):
        if not flags & omitted:
            if reader.take(1)[0]:
                reader.take(4 if mode == 0 else 2)
    if any(not math.isfinite(v) or abs(v) > 2**30 for v in position):
        raise CryptoError('Received physics position exceeds supported range.')
    return {'position': position, 'rotation_code': rotation}


def stationary_item(root, position, *, humanoid_state=8):
    """Native 0x1057bddf0/0x1057beaa0: current root, zero motors/speeds.

    This serializes an actual outgoing movement request. It does not mutate
    the receive-side world or establish that a server accepted the request.
    """
    if (not isinstance(root, tuple) or len(root) != 2 or
            any(type(v) is not int for v in root) or not 1 <= root[0] <= 0xffffffff or
            not 0 <= root[1] <= 0xffffffff or type(humanoid_state) is not int or
            not 0 <= humanoid_state <= 31):
        raise CryptoError('Unsupported physics root or humanoid state.')
    # Identity orientation, native packed quaternion. Speeds omitted by 0x60.
    pv = b'\x60' + coordinates(position) + bytes.fromhex('0000000000c0')
    if all(v == 0 for v in position):
        pv = b'\xe0' + bytes.fromhex('0000000000c0')
    return (varuint(root[0]) + struct.pack('<I', root[1]) + b'\0\1' +
            bytes([0x20 | humanoid_state]) + b'\0' + pv + b'\0')


def stationary_packet(root, position, timestamp, sequence, capabilities):
    if any(type(v) is not int or not 0 <= v < 2**64 for v in (timestamp, sequence, capabilities)):
        raise CryptoError('Unsupported physics envelope values.')
    # Native 0x1057bdb7c. Capability bit 25 changes where the sequence sits.
    if capabilities & 0x2000000:
        header = b'\x1b' + struct.pack('<Q', timestamp) + b'\x85' + struct.pack('<Q', sequence)
    else:
        header = b'\x1b' + struct.pack('<QQ', timestamp, sequence) + b'\x85'
    return header + stationary_item(root, position) + b'\0'

"""Bounded RakNet datagram/frame codec for the recovered connected transport."""

from dataclasses import dataclass
import struct
import time

from .native_crypto import CryptoError


def u24(value: int) -> bytes:
    if type(value) is not int or not 0 <= value < 2**24:
        raise CryptoError("RakNet sequence must fit uint24.")
    return value.to_bytes(3, "little")


@dataclass(repr=False)
class Frame:
    payload: bytes
    reliability: int
    reliable_index: int | None = None
    order_index: int | None = None
    channel: int = 0
    split: tuple[int, int, int] | None = None

    def __repr__(self):
        return f"Frame(bytes={len(self.payload)}, reliability={self.reliability})"


def frame(payload: bytes, *, reliability: int = 2, reliable_index: int = 0,
          order_index: int = 0, channel: int = 0, split: tuple[int, int, int] | None = None) -> bytes:
    if reliability not in (0, 2, 3) or not payload or len(payload) > 8191 or not 0 <= channel <= 31:
        raise CryptoError("Unsupported outgoing RakNet frame.")
    out = bytes([(reliability << 5) | (0x10 if split is not None else 0)]) + struct.pack(">H", len(payload) * 8)
    if reliability in (2, 3):
        out += u24(reliable_index)
    if reliability == 3:
        out += u24(order_index) + bytes([channel])
    if split is not None:
        split_id, count, index = split
        if not 0 <= split_id < 65536 or not 0 <= index < count <= 4096:
            raise CryptoError("Invalid outgoing split bounds.")
        out += struct.pack(">IHI", count, split_id, index)
    return out + payload


def datagram(payload: bytes, sequence: int) -> bytes:
    return b"\x84" + u24(sequence) + payload


def ack(sequence: int) -> bytes:
    return b"\xc0\0\x01\x01" + u24(sequence)


def ack_many(sequences) -> bytes:
    """Acknowledge only received datagrams, without filling holes or wrap gaps."""
    if not sequences or len(sequences) > 128:
        raise CryptoError('ACK batch must contain 1..128 sequences.')
    for value in sequences:
        if type(value) is not int or not 0 <= value < 2**24:
            raise CryptoError('Invalid ACK sequence.')
    values = sorted(set(sequences))
    ranges = []
    first = last = values[0]
    for value in values[1:]:
        if value == last + 1:
            last = value
        else:
            ranges.append((first, last))
            first = last = value
    ranges.append((first, last))
    return b'\xc0' + struct.pack('>H', len(ranges)) + b''.join(
        b'\1' + u24(first) if first == last else b'\0' + u24(first) + u24(last)
        for first, last in ranges)


def nack_many(sequences) -> bytes:
    return b'\xa0' + ack_many(sequences)[1:]


class DatagramLoss:
    """Bounded, one-shot NAKs after a short datagram reordering grace period."""
    def __init__(self, *, window=4096, delay=0.005):
        self.window, self.delay = window, delay
        self.highest = None
        self.missing = {}
        self.detected = self.reported = 0

    def receive(self, sequence, now):
        u24(sequence)
        self.missing.pop(sequence, None)
        if self.highest is None:
            self.highest = sequence
            return
        distance = (sequence - self.highest) & 0xffffff
        if 0 < distance < 0x800000:
            if distance > self.window:
                raise CryptoError('RakNet datagram loss window exceeded.')
            for offset in range(1, distance):
                self.missing[(self.highest + offset) & 0xffffff] = now
            self.detected += distance - 1
            self.highest = sequence
            # Old transmissions cannot be recovered once the peer's send
            # window has moved on. Never accumulate holes for an entire run.
            self.missing = {n: at for n, at in self.missing.items()
                            if ((sequence - n) & 0xffffff) <= self.window}

    def due(self, now):
        ready = [n for n, at in self.missing.items() if now - at >= self.delay][:128]
        for sequence in ready:
            del self.missing[sequence]
        self.reported += len(ready)
        return ready


def decode(packet: bytes) -> tuple[int | None, list[Frame]]:
    if len(packet) < 4 or not packet[0] & 0x80:
        raise CryptoError("Truncated RakNet connected datagram.")
    if packet[0] & 0x60:
        return None, []  # ACK/NAK records are handled separately by a sender.
    sequence = int.from_bytes(packet[1:4], "little")
    cursor = 4
    frames = []

    def take(size):
        nonlocal cursor
        if size < 0 or cursor + size > len(packet):
            raise CryptoError("Truncated RakNet frame.")
        value = packet[cursor:cursor + size]
        cursor += size
        return value

    while cursor < len(packet):
        flags = take(1)[0]
        reliability = flags >> 5
        bits = int.from_bytes(take(2), "big")
        reliable = int.from_bytes(take(3), "little") if reliability in (2, 3, 4, 6, 7) else None
        if reliability in (1, 4):
            take(3)  # sequencing index
        order = int.from_bytes(take(3), "little") if reliability in (1, 3, 4, 7) else None
        channel = take(1)[0] if order is not None else 0
        if channel > 31:
            raise CryptoError("Invalid RakNet ordering channel.")
        split = None
        if flags & 0x10:
            count = int.from_bytes(take(4), "big")
            split_id = int.from_bytes(take(2), "big")
            index = int.from_bytes(take(4), "big")
            if not 0 <= index < count <= 4096:
                raise CryptoError("Invalid RakNet split bounds.")
            split = (split_id, count, index)
        payload = take((bits + 7) // 8)
        if not payload:
            raise CryptoError("Empty RakNet message.")
        frames.append(Frame(payload, reliability, reliable, order, channel, split))
    return sequence, frames


def acknowledgements(packet: bytes) -> tuple[bool, list[tuple[int, int]]]:
    """Decode bounded ACK/NAK intervals, allowing native trailing statistics."""
    if len(packet) < 3 or packet[0] & 0xe0 not in (0xa0, 0xc0):
        raise CryptoError("Invalid RakNet acknowledgement.")
    count = int.from_bytes(packet[1:3], "big")
    if count > 4096:
        raise CryptoError("Too many acknowledgement records.")
    cursor, ranges = 3, []
    for _ in range(count):
        if cursor + 4 > len(packet) or packet[cursor] not in (0, 1):
            raise CryptoError("Truncated acknowledgement record.")
        single = packet[cursor]
        first = int.from_bytes(packet[cursor + 1:cursor + 4], "little")
        cursor += 4
        last = first
        if not single:
            if cursor + 3 > len(packet):
                raise CryptoError("Truncated acknowledgement range.")
            last = int.from_bytes(packet[cursor:cursor + 3], "little")
            cursor += 3
        if last < first:
            raise CryptoError("Invalid acknowledgement range.")
        ranges.append((first, last))
    return bool(packet[0] & 0x40), ranges


class Assembler:
    """Bound split storage, suppress reliable duplicates and deliver in order.

    A missing reliable fragment is recovered by the peer's retransmission;
    expiring an incomplete reliable message fails the connection explicitly.
    """

    def __init__(self, *, byte_limit=8 * 1024 * 1024, ttl=20):
        self.byte_limit, self.ttl = byte_limit, ttl
        self._splits = {}
        self._ordered = {}
        self._next_order = [0] * 32
        self._seen = set()
        self._highest = None
        self._bytes = 0

    def push(self, item: Frame, now=None) -> list[bytes]:
        now = time.monotonic() if now is None else now
        if any(now - group[0] > self.ttl for group in self._splits.values()):
            raise CryptoError("Incomplete RakNet message expired.")
        if item.reliable_index is not None:
            index = item.reliable_index
            if index in self._seen:
                return []
            if self._highest is not None:
                distance = (index - self._highest) & 0xffffff
                if distance >= 0x800000 and ((self._highest - index) & 0xffffff) > 8192:
                    return []
                if 0 < distance < 0x800000:
                    self._highest = index
            else:
                self._highest = index
            self._seen.add(index)
            if len(self._seen) > 16384:
                self._seen = {n for n in self._seen if ((self._highest - n) & 0xffffff) <= 8192}
        payload = item.payload
        if item.split is not None:
            split_id, count, index = item.split
            if not 0 <= index < count <= 4096:
                raise CryptoError("Invalid RakNet split bounds.")
            group = self._splits.get(split_id)
            meta = (count, item.reliability, item.order_index, item.channel)
            if group is None:
                if len(self._splits) >= 128:
                    raise CryptoError("Too many incomplete RakNet messages.")
                group = (now, meta, {})
                self._splits[split_id] = group
            if group[1] != meta:
                raise CryptoError("Conflicting RakNet split metadata.")
            chunks = group[2]
            if index in chunks:
                if chunks[index] != payload:
                    raise CryptoError("Conflicting RakNet split data.")
                return []
            self._bytes += len(payload)
            if self._bytes > self.byte_limit:
                raise CryptoError("RakNet receive buffer limit exceeded.")
            chunks[index] = payload
            if len(chunks) != count:
                return []
            payload = b"".join(chunks[n] for n in range(count))
            del self._splits[split_id]
            self._bytes -= len(payload)
        if item.reliability not in (3, 7):
            if item.reliability in (1, 4):
                raise CryptoError("Sequenced delivery is not implemented.")
            return [payload]
        expected = self._next_order[item.channel]
        distance = (item.order_index - expected) & 0xffffff
        if distance >= 0x800000:
            return []
        if distance > 4096:
            raise CryptoError("RakNet ordering window exceeded.")
        key = (item.channel, item.order_index)
        if key not in self._ordered:
            self._ordered[key] = payload
            self._bytes += len(payload)
        if self._bytes > self.byte_limit:
            raise CryptoError("RakNet receive buffer limit exceeded.")
        out = []
        while (item.channel, expected) in self._ordered:
            ready = self._ordered.pop((item.channel, expected))
            self._bytes -= len(ready)
            out.append(ready)
            expected = (expected + 1) & 0xffffff
        self._next_order[item.channel] = expected
        return out

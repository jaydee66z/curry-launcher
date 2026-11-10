"""Bounded attribute and game Buff readers; unknown variants fail closed."""
import struct


class Reader:
    def __init__(self, raw):
        if not isinstance(raw, bytes) or len(raw) > 1048576:
            raise ValueError('Invalid game data size')
        self.raw, self.at, self.items = raw, 0, 0

    def take(self, count):
        if not 0 <= count <= len(self.raw) - self.at:
            raise ValueError('Truncated game data')
        result = self.raw[self.at:self.at + count]
        self.at += count
        return result

    def integer(self, size):
        return int.from_bytes(self.take(size), 'little')

    def string(self, size=4):
        return self.take(self.integer(size))


def attributes(raw):
    # rbx-dom/docs/attributes.md; the network's AttributesReplicate uses
    # the same count + name/type/value representation for these primitives.
    if not raw:
        return {}
    reader, result = Reader(raw), {}
    count = reader.integer(4)
    if count > 256:
        raise ValueError('Attribute count exceeds bound')
    for _ in range(count):
        name, kind = reader.string(), reader.integer(1)
        if name in result:
            raise ValueError('Duplicate attribute')
        if kind == 2:
            value = reader.string()
        elif kind == 3:
            value = bool(reader.integer(1))
        elif kind in (4, 5, 6):
            value = struct.unpack({4: '<i', 5: '<f', 6: '<d'}[kind], reader.take(8 if kind == 6 else 4))[0]
        else:
            raise ValueError('Unsupported attribute variant')
        result[name] = value
    if reader.at != len(raw):
        raise ValueError('Attribute trailing data')
    return result


def buff(raw, instances=()):
    """Observed ReplicatorClient.Buff tags 0..17/21/92, without executing it."""
    reader = Reader(raw)

    def value(depth=0):
        reader.items += 1
        if depth > 24 or reader.items > 65536:
            raise ValueError('Game Buff nesting/item limit')
        kind = reader.integer(1)
        if kind <= 2:
            return (None, True, False)[kind]
        formats = {3: ('<B', 1), 4: ('<H', 2), 5: ('<I', 4), 6: ('<b', 1),
                   7: ('<h', 2), 8: ('<i', 4), 9: ('<d', 8)}
        if kind in formats:
            fmt, length = formats[kind]
            return struct.unpack(fmt, reader.take(length))[0]
        if kind in (10, 11, 12, 13):
            return reader.string({10: 1, 11: 2, 12: 4, 13: 4}[kind])
        if kind == 16:
            return {}
        if kind == 17:
            count = reader.integer(4)
            if count > 65536:
                raise ValueError('Game Buff array exceeds bound')
            return [value(depth + 1) for _ in range(count)]
        if kind == 21:
            result = {}
            while reader.at < len(raw) and raw[reader.at] != 255:
                key = value(depth + 1)
                if type(key) not in (bytes, int, float, bool) or key in result:
                    raise ValueError('Invalid game Buff dictionary key')
                result[key] = value(depth + 1)
            if reader.integer(1) != 255:
                raise ValueError('Missing game Buff dictionary terminator')
            return result
        if kind == 92:
            index = reader.integer(4)
            if not 1 <= index <= len(instances):
                raise ValueError('Invalid game Buff instance index')
            return instances[index - 1]
        raise ValueError('Unsupported game Buff tag')

    result = value()
    if reader.at != len(raw):
        raise ValueError('Game Buff trailing data')
    return result

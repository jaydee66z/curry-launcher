"""Minimal native Data/Ping response, distinct from RakNet transport pong."""
import struct

from .native_crypto import CryptoError


def pong(timestamp, server_tick, received_tick, prepared_tick, sent_tick, *, large=False,
         local_counter=0, local_pair=(0, 0)):
    """Native 0x10580dcfa / 0x10580ddfc, ordinary item IDs, no optional blobs.

    Zero local error report is an empty report from this implementation. Engine
    statistics unavailable in this headless client are left at their initial 0.
    The clock samples must come from the actual receive/send path.
    """
    fields = (server_tick, received_tick, prepared_tick, sent_tick,
              local_counter, *local_pair, 0, 0xffffffff if timestamp & 0x20 else 0)
    if (type(timestamp) is not int or not 0 <= timestamp < 2**64 or
            len(fields) != 9 or any(type(x) is not int or not 0 <= x < 2**32 for x in fields) or
            type(large) is not bool):
        raise CryptoError('Invalid Data/Ping response fields.')
    return b'\x83\x06\x01' + struct.pack('<Q9I', timestamp, *fields) + bytes([large, 0])

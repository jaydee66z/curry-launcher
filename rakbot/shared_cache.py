"""Bounded, verified shared-string cache for the native A7 inventory protocol."""
from collections import OrderedDict, deque
import hashlib
import os
from pathlib import Path
import struct
import threading

from .native_crypto import CryptoError

CAPABILITY = 1 << 44
MAX_ENTRIES = 8192
# Egg worlds send about 24 MiB of shared assets before a snapshot reply. The
# ordinary 8 MiB LRU evicts most of that inventory on every server transition.
PLACE_BYTE_LIMITS = {107778070777162: 32 * 1024 * 1024}
_caches = OrderedDict()
_lock = threading.Lock()


class SharedCache:
    def __init__(self, byte_limit=8 * 1024 * 1024):
        self.limit = byte_limit
        self.entries = OrderedDict()
        self.size = 0
        self.lock = threading.Lock()
        self.rtts = deque(maxlen=64)

    def add(self, digest, blob):
        if (not isinstance(digest, bytes) or len(digest) != 16 or not isinstance(blob, bytes)
                or not 256 <= len(blob) <= 1048576):
            return
        if hashlib.blake2b(blob, digest_size=16).digest() != digest:
            raise CryptoError('Invalid shared-string cache checksum.')
        with self.lock:
            if digest in self.entries:
                self.entries.move_to_end(digest)
                return
            if len(blob) > self.limit:
                return
            while self.entries and (self.size + len(blob) > self.limit or len(self.entries) >= MAX_ENTRIES):
                _, previous = self.entries.popitem(last=False)
                self.size -= len(previous)
            self.entries[digest] = blob
            self.size += len(blob)

    def snapshot(self):
        # Bytes are immutable and referenced, not copied. A live connection
        # retains its advertised snapshot even if later joins evict cache rows.
        with self.lock:
            return dict(self.entries)

    def get(self, digest):
        with self.lock:
            return self.entries.get(digest)

    def observe_rtt(self, seconds):
        if type(seconds) in (int, float) and 0 < seconds < 3:
            with self.lock:
                self.rtts.append(seconds)

    def rtt_limit(self):
        with self.lock:
            return max(0.18, min(self.rtts) * 1.8 + 0.03) if self.rtts else None

    def load(self, path, place_id):
        maximum = self.limit + MAX_ENTRIES * 20 + 20
        try:
            with path.open('rb') as file:
                data = file.read(maximum + 1)
            if len(data) < 20 or len(data) > maximum or data[:8] != b'RBCACHE1':
                return False
            stored_place, count = struct.unpack_from('<QI', data, 8)
            if stored_place != place_id or count > MAX_ENTRIES:
                return False
            at, size, entries = 20, 0, OrderedDict()
            for _ in range(count):
                if at + 20 > len(data):
                    return False
                digest = data[at:at + 16]
                length = struct.unpack_from('<I', data, at + 16)[0]
                at += 20
                if not 256 <= length <= 1048576 or at + length > len(data):
                    return False
                blob = data[at:at + length]
                at += length
                size += length
                if size > self.limit or digest in entries or hashlib.blake2b(blob, digest_size=16).digest() != digest:
                    return False
                entries[digest] = blob
            if at != len(data):
                return False
        except (OSError, ValueError, struct.error):
            return False
        with self.lock:
            self.entries, self.size = entries, size
        return True

    def save(self, path, place_id):
        entries = self.snapshot()
        if not entries:
            return
        data = b'RBCACHE1' + struct.pack('<QI', place_id, len(entries)) + b''.join(
            digest + struct.pack('<I', len(blob)) + blob for digest, blob in entries.items())
        temporary = path.with_name(f'{place_id}-{os.getpid()}-{threading.get_ident()}.tmp')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(data)
            os.replace(temporary, path)
        except OSError:
            pass  # A read-only install still works with the bounded RAM cache.
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _cache_path(place_id):
    return Path(__file__).resolve().parents[1] / '.rakbot-cache' / f'{place_id}.bin'


def for_place(place_id):
    with _lock:
        cache = _caches.get(place_id)
        if cache is None:
            cache = _caches[place_id] = SharedCache(PLACE_BYTE_LIMITS.get(place_id,8 * 1024 * 1024))
            cache.load(_cache_path(place_id), place_id)
            while len(_caches) > 3:
                _caches.popitem(last=False)
        _caches.move_to_end(place_id)
        return cache


def save_all():
    with _lock:
        caches = list(_caches.items())
    for place, cache in caches:
        cache.save(_cache_path(place), place)


def advertisement(snapshot):
    if not isinstance(snapshot, dict) or len(snapshot) > MAX_ENTRIES:
        raise CryptoError('Shared-string cache inventory exceeds bound.')
    if not snapshot:
        return None  # Native 0x1058d5372 sends nothing for an empty cache.
    if any(not isinstance(key, bytes) or len(key) != 16 for key in snapshot):
        raise CryptoError('Invalid shared-string cache inventory hash.')
    # Native writer 0x1058d5372, untagged variant, capability bit 29 absent.
    return b'\xa7' + struct.pack('<H', len(snapshot)) + b''.join(snapshot)

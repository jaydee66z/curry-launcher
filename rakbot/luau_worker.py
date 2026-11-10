"""Prestarted isolated VM, bounded binary pipes; no filesystem round-trip per reply."""

import queue
import re
import struct
import subprocess
import threading
import time

from .luau_bytecode import ROOT, inspect, unpack_rsb
from .bootstrap import job_id


class HopBridgeError(ValueError):
    """Sanitized failure of the local trusted Luau teleport adapter."""


class Worker:
    def __init__(self):
        self.process = None
        self._reader = None
        self._results = queue.Queue(maxsize=2)
        self.last_elapsed_ms = None

    def __enter__(self):
        executable = ROOT / '.reverse-inputs/luau-probe-build/Release/rakbot-luau-probe.exe'
        self.process = subprocess.Popen([str(executable), '--worker'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        try:
            if self._receive(3) != b'RBVM':
                raise ValueError('Unsupported isolated VM worker')
            # Import and header reads happen before a live transport is opened.
            from compression import zstd
            self._headers = ROOT / '.reverse-inputs/luau/Common/include/Luau'
            for name in ('Bytecode.h', 'BytecodeUtils.h'):
                (self._headers / name).read_text(encoding='utf-8')
        except BaseException:
            self.close()
            raise
        return self

    def _read(self):
        try:
            size = 4
            while True:
                data = bytearray()
                while len(data) < size:
                    piece = self.process.stdout.read(size - len(data))
                    if not piece:
                        raise EOFError
                    data.extend(piece)
                self._results.put(bytes(data), timeout=0.5)
                size = 16
        except (OSError, ValueError, EOFError, queue.Full):
            try:
                self._results.put_nowait(None)
            except queue.Full:
                pass

    def _receive(self, timeout):
        try:
            result = self._results.get(timeout=timeout)
        except queue.Empty:
            raise ValueError('Isolated VM worker timed out') from None
        if result is None:
            raise ValueError('Isolated VM worker stopped')
        return result

    def reply(self, packet, job_id):
        started = time.perf_counter()
        if self.process is None or self.process.poll() is not None:
            raise ValueError('Isolated VM worker is not running')
        if (not 13 <= len(packet) <= 1048576 or packet[0] != 0x9b or
                not isinstance(job_id, str) or (job_id != '' and not re.fullmatch(r'[0-9a-fA-F-]{36}', job_id))):
            raise ValueError('Unsupported execution-request context')
        first, second, size = struct.unpack_from('<III', packet, 1)
        if size != len(packet) - 13:
            raise ValueError('Unsupported execution-request envelope')
        raw = unpack_rsb(packet[13:])
        code = bytearray(raw)
        inspect(raw, self._headers, normalized=code)
        job = job_id.encode('ascii')
        frame = struct.pack('<IIII', len(code), second, first, len(job)) + job + code
        try:
            pending = memoryview(frame)
            while pending:
                sent = self.process.stdin.write(pending)
                if not sent:
                    raise OSError
                pending = pending[sent:]
            self.process.stdin.flush()
            result = self._receive(0.5)
        except (OSError, ValueError):
            self.close()
            raise ValueError('Isolated VM worker could not complete the request') from None
        self.last_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        status, numeric, missing, reserved = result[:4]
        if status != 0 or numeric != 1 or missing != 0 or reserved != 0:
            self.close()
            raise ValueError('Isolated VM did not complete with fully supported APIs')
        return b'\x9b' + struct.pack('<I', second) + result[4:8]

    def teleport(self, place_id, target, current, user_id):
        """Run the local Luau TeleportService adapter; never execute server code."""
        target, current = job_id(target), job_id(current)
        if (type(place_id) is not int or not 0 < place_id < 2**53 or
                type(user_id) is not int or not 0 < user_id < 2**53 or target == current):
            raise HopBridgeError('Invalid local Luau teleport context.')
        if self.process is None or self.process.poll() is not None:
            raise HopBridgeError('Local Luau teleport VM is not running.')
        frame = (struct.pack('<IIII', 0, place_id & 0xffffffff, place_id >> 32, 36) +
                 target.encode('ascii') + current.encode('ascii') + struct.pack('<Q', user_id))
        started = time.perf_counter()
        try:
            pending = memoryview(frame)
            while pending:
                sent = self.process.stdin.write(pending)
                if not sent:
                    raise OSError
                pending = pending[sent:]
            self.process.stdin.flush()
            result = self._receive(0.5)
            if result != b'\0\1\0\0' + struct.pack('<III', 1, 0, 0):
                raise ValueError
        except (OSError, ValueError):
            self.close()
            raise HopBridgeError('Luau teleport bridge unavailable; update the bundled native VM executable.') from None
        self.last_hop_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        return {'state': 'teleport_requested', 'via': 'local_luau_adapter',
                'place_id': place_id, 'job_id': target, 'user_id': user_id}

    def close(self):
        if self.process is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            try:
                self.process.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
            self.process.stdout.close()
        if self._reader is not None:
            self._reader.join(timeout=0.5)

    def __exit__(self, *args):
        self.close()

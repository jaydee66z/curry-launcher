"""Bounded terminal input; the network thread alone executes commands."""

import queue
import sys
import threading


class Console:
    def __init__(self, stream, *, prompt='rakbot> '):
        self.stream = stream
        self.prompt = prompt
        self.commands = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._reader = None
        self._output_lock = threading.RLock()
        self._line = []
        self._terminal = sys.platform == 'win32' and stream.isatty()

    def emit(self, message):
        """Preserve the editable input line when a network event is printed."""
        self.emit_many([message])

    def set_title(self, title):
        if not self._terminal:
            return
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.SetConsoleTitleW.argtypes = (wintypes.LPCWSTR,)
            kernel.SetConsoleTitleW.restype = wintypes.BOOL
            kernel.SetConsoleTitleW(title[:2048])
        except (OSError, AttributeError):
            pass

    def emit_many(self, messages):
        if not messages:
            return
        with self._output_lock:
            if self._terminal:
                current = self.prompt + ''.join(self._line)
                sys.stderr.write('\r' + ' ' * len(current) + '\r')
            sys.stderr.write('\n'.join(messages) + '\n')
            if self._terminal:
                sys.stderr.write(current)
            sys.stderr.flush()

    def _put(self, command):
        while not self._stop.is_set():
            try:
                self.commands.put(command, timeout=0.1)
                return
            except queue.Full:
                pass

    def _read(self):
        if self._terminal:
            self._read_windows_terminal()
            return
        while not self._stop.is_set():
            try:
                line = self.stream.readline(4098)
            except (OSError, ValueError):
                line = ''
            if line == '':
                self._put('quit')
                return
            if len(line) > 4096:
                while line and not line.endswith('\n'):
                    line = self.stream.readline(4098)
                self._put('__oversized_command__')
            elif line.strip():
                self._put(line.strip())

    def _read_windows_terminal(self):
        # A blocking stdin.readline daemon can retain the terminal lock during
        # interpreter shutdown. Poll console keys so quit can stop this reader.
        import msvcrt
        oversized, extended = False, False
        with self._output_lock:
            sys.stderr.write(self.prompt)
            sys.stderr.flush()
        while not self._stop.is_set():
            if not msvcrt.kbhit():
                self._stop.wait(0.02)
                continue
            char = msvcrt.getwch()
            command = None
            with self._output_lock:
                if extended:
                    extended = False
                    continue
                if char in ('\0', '\xe0'):
                    extended = True
                elif char in ('\x1b', '\x15'):
                    sys.stderr.write('\r' + ' ' * (len(self.prompt) + len(self._line)) + '\r' + self.prompt)
                    self._line.clear()
                    oversized = False
                elif char in ('\x03', '\x1a'):
                    command = 'quit'
                elif char in ('\r', '\n'):
                    sys.stderr.write('\n')
                    command = '__oversized_command__' if oversized else ''.join(self._line).strip()
                    self._line.clear()
                    oversized = False
                    sys.stderr.write(self.prompt)
                elif char == '\b' and self._line and not oversized:
                    self._line.pop()
                    sys.stderr.write('\b \b')
                elif char.isprintable() and not oversized:
                    self._line.append(char)
                    sys.stderr.write(char)
                    oversized = len(self._line) > 4096
                sys.stderr.flush()
            if command:
                self._put(command)
                if command == 'quit':
                    return

    def __enter__(self):
        self._reader = threading.Thread(target=self._read, daemon=True, name='rakbot-console')
        self._reader.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._reader.join(timeout=0.1)
        if self._terminal:
            with self._output_lock:
                sys.stderr.write('\r' + ' ' * (len(self.prompt) + len(self._line)) + '\r')
                sys.stderr.flush()

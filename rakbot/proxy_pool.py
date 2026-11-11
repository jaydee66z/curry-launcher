"""Proxy pool — 1 line per account, pinned round-robin.

Input file (gitignored): ``proxies.txt`` or ``proxies.local.txt`` next
to ``cookies.txt``. Format is a plain list, one proxy per line. Lines
starting with ``#`` and blanks are ignored. Accepted shapes::

    LOGIN:PASS@HOST:PORT                       (bare user/pass)
    http://LOGIN:PASS@HOST:PORT                (explicit scheme)
    HOST:PORT                                  (no auth)
    HOST:PORT:LOGIN:PASS                       (host-first w/ auth)

Example (DataImpulse port-per-slot list)::

    7b6836727aba3489492b__cr.sg,ca,de:3325242df89fce79@gw.dataimpulse.com:10000
    7b6836727aba3489492b__cr.sg,ca,de:3325242df89fce79@gw.dataimpulse.com:10001
    ... one line per sticky slot (one slot = one pinned IP)

Each ``account_id`` maps to ONE line by stable hash → that account
always uses the same proxy slot across restarts. If more accounts
than lines, we round-robin (lines reused).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_DEFAULT_PATHS = ("proxies.txt", "proxies.local.txt", "proxies.list")


def _parse_line(raw: str) -> Optional[str]:
    """Normalize one proxy line into ``http://user:pass@host:port`` (or no auth)."""
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith(("http://", "https://", "socks5://", "socks4://")):
        return line  # already a full URL
    # Shape: HOST:PORT:LOGIN:PASS
    m = re.fullmatch(r"([^\s:@]+):(\d+):([^\s:@]+):([^\s@]+)", line)
    if m:
        host, port, user, pwd = m.groups()
        return f"http://{user}:{pwd}@{host}:{port}"
    # Shape: LOGIN:PASS@HOST:PORT
    if "@" in line:
        return f"http://{line}"
    # Shape: HOST:PORT (no auth)
    m = re.fullmatch(r"([^\s:@]+):(\d+)", line)
    if m:
        host, port = m.groups()
        return f"http://{host}:{port}"
    return None


class ProxyPool:
    """One proxy per account, pinned by stable hash of account id."""

    def __init__(self, path: Optional[str | Path] = None):
        self._lines: list[str] = []
        if path is None:
            for candidate in _DEFAULT_PATHS:
                if Path(candidate).exists():
                    path = candidate
                    break
        if path is not None and Path(path).exists():
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        for raw in path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(raw)
            if parsed:
                self._lines.append(parsed)

    def enabled(self) -> bool:
        return len(self._lines) > 0

    def count(self) -> int:
        return len(self._lines)

    def url_for(self, account_id: int) -> Optional[str]:
        """Return the proxy URL pinned to this account id.

        Mapping is ``account_id % len(lines)`` — stable across restarts
        so the same Roblox account always exits through the same IP.
        """
        if not self._lines:
            return None
        idx = int(account_id) % len(self._lines)
        return self._lines[idx]

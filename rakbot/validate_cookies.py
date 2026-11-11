"""Validate cookies.txt against Roblox auth — classify live / dead / ratelimit.

Usage::

    python -m rakbot.validate_cookies --cookies cookies.txt \
        --proxies proxies.txt --workers 50

Writes three files next to cookies.txt::

    cookies.live.txt        <user_id>\\t<cookie>
    cookies.dead.txt        <reason>\\t<cookie_prefix>...
    cookies.ratelimit.txt   <cookie>           (retry later)
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from .bootstrap import (
    IDENTITY_URL, BootstrapError, Credential, NetworkUnavailable,
    RateLimited, RobloxHTTP,
)
from .mass import read_mass_credentials, MAX_ACCOUNTS
from .proxy_pool import ProxyPool


def _preview(cookie: str) -> str:
    return cookie[:12] + "..." + cookie[-6:] if len(cookie) > 30 else "(short)"


def check_one(idx: int, cookie: str, pool: ProxyPool) -> tuple[str, int, str]:
    """Return (status, user_id_or_0, cookie)."""
    try:
        cred = Credential(cookie)
    except BootstrapError:
        return ("dead:parse", 0, cookie)
    proxy_url = pool.url_for(idx) if pool.enabled() else None
    http = RobloxHTTP(proxy_url=proxy_url)
    try:
        reply = http.request(IDENTITY_URL, credential=cred)
    except RateLimited:
        return ("ratelimit", 0, cookie)
    except (NetworkUnavailable, BootstrapError):
        return ("dead:network", 0, cookie)
    except Exception as e:
        return (f"dead:{type(e).__name__}", 0, cookie)
    if reply.status == 200:
        try:
            data = json.loads(reply.body)
            uid = int(data.get("id", 0))
            if uid > 0:
                return ("live", uid, cookie)
        except (ValueError, TypeError):
            pass
        return ("dead:parse_response", 0, cookie)
    if reply.status == 401:
        return ("dead:401", 0, cookie)
    if reply.status == 403:
        return ("dead:403", 0, cookie)
    if reply.status == 429:
        return ("ratelimit", 0, cookie)
    return (f"dead:{reply.status}", 0, cookie)


def main() -> int:
    p = argparse.ArgumentParser(description="Validate cookies.txt.")
    p.add_argument("--cookies", default="cookies.txt")
    p.add_argument("--proxies", default="proxies.txt")
    p.add_argument("--workers", type=int, default=50, help="parallel checks (1..200)")
    p.add_argument("--max", type=int, default=MAX_ACCOUNTS, help="max cookies to check")
    args = p.parse_args()
    if not 1 <= args.workers <= 200:
        print("--workers must be 1..200", file=sys.stderr)
        return 2

    credentials = read_mass_credentials(args.cookies, args.max)
    pool = ProxyPool(args.proxies)
    total = len(credentials)
    print(f"[validate] {total} cookies loaded, pool_enabled={pool.enabled()} "
          f"({pool.count()} slots), workers={args.workers}")

    live_path = Path("cookies.live.txt")
    dead_path = Path("cookies.dead.txt")
    rl_path   = Path("cookies.ratelimit.txt")
    counts = {"live": 0, "ratelimit": 0, "dead": 0}
    t0 = time.time()
    with (live_path.open("w", encoding="utf-8") as fl,
          dead_path.open("w", encoding="utf-8") as fd,
          rl_path.open("w", encoding="utf-8") as fr):
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(check_one, i, c.value, pool): i
                       for i, c in enumerate(credentials)}
            done = 0
            for fut in cf.as_completed(futures):
                done += 1
                status, uid, cookie = fut.result()
                if status == "live":
                    fl.write(f"{uid}\t{cookie}\n")
                    counts["live"] += 1
                elif status == "ratelimit":
                    fr.write(f"{cookie}\n")
                    counts["ratelimit"] += 1
                else:
                    fd.write(f"{status}\t{_preview(cookie)}\n")
                    counts["dead"] += 1
                if done % 25 == 0 or done == total:
                    elapsed = time.time() - t0
                    rate = done / max(0.01, elapsed)
                    print(f"[validate] {done}/{total}  "
                          f"live={counts['live']} rl={counts['ratelimit']} "
                          f"dead={counts['dead']}  ({rate:.1f}/s)")

    print(f"[validate] done: live={counts['live']} dead={counts['dead']} rl={counts['ratelimit']}")
    print(f"           wrote {live_path}, {dead_path}, {rl_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

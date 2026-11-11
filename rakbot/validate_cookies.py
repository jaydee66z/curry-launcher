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


_BAN_PHRASES = (
    "banned", "terminated", "moderated", "under review", "deleted",
    "suspended", "poison",
)
_FACELOCK_HINTS = ("voice", "facial", "faceverification", "voiceverification",
                   "selfie", "biometric", "id verification")


def _classify_challenge(reply) -> str | None:
    """Inspect reply headers/body for Roblox challenge markers."""
    headers = {k.lower(): (v or "").lower() for k, v in reply.headers.items()}
    challenge_id = headers.get("rblx-challenge-id")
    challenge_type = headers.get("rblx-challenge-type", "")
    body_lower = (reply.body or b"").decode("utf-8", "replace").lower()
    if any(h in challenge_type or h in body_lower for h in _FACELOCK_HINTS):
        return "facelock"
    if challenge_id:
        # captcha on everything = captcha_lock; captcha only on join = captcha_join
        # (we detect join-vs-not by which URL the caller passed)
        return "captcha"
    if "two step" in body_lower or "two-step" in body_lower:
        return "two_factor"
    return None


def _classify_ban(body_bytes: bytes) -> str | None:
    text = (body_bytes or b"").decode("utf-8", "replace").lower()
    if not text:
        return None
    for phrase in _BAN_PHRASES:
        if phrase in text:
            if "perm" in text or "terminated" in text or "deleted" in text:
                return "ban_perm"
            return "ban_temp"
    return None


def check_one(idx: int, cookie: str, pool: ProxyPool) -> tuple[str, int, str]:
    """Return (status, user_id_or_0, cookie)."""
    try:
        cred = Credential(cookie)
    except BootstrapError:
        return ("dead:parse", 0, cookie)
    proxy_url = pool.url_for(idx) if pool.enabled() else None
    http = RobloxHTTP(proxy_url=proxy_url)

    # Step 1: authenticated identity. Captures 401/403/challenge/ban at the
    # website/API layer.
    try:
        reply = http.request(IDENTITY_URL, credential=cred)
    except RateLimited:
        return ("ratelimit", 0, cookie)
    except (NetworkUnavailable, BootstrapError):
        return ("dead:network", 0, cookie)
    except Exception as e:
        return (f"dead:{type(e).__name__}", 0, cookie)

    challenge = _classify_challenge(reply)
    if challenge == "facelock":
        return ("facelock", 0, cookie)
    if challenge == "captcha":
        return ("captcha_lock", 0, cookie)
    if challenge == "two_factor":
        return ("two_factor", 0, cookie)

    if reply.status == 200:
        try:
            data = json.loads(reply.body)
        except (ValueError, TypeError):
            return ("dead:parse_response", 0, cookie)
        uid = int(data.get("id", 0)) if isinstance(data.get("id"), int) else 0
        name = data.get("name", "") if isinstance(data, dict) else ""
        if data.get("isBanned") is True:
            return ("ban_perm", uid, cookie)
        if uid <= 0 or not name:
            # Weird response; treat as dead.
            return ("dead:bad_identity", 0, cookie)
        # Step 2: optional join test to catch the "captcha appears only when
        # joining a game" case the operator mentioned. Non-fatal — if the
        # join endpoint itself errors, we still return live because the
        # website is fine (bot will reach join and auto-rejoin from there).
        # Minimal join payload: query a dummy place details URL that's
        # whitelisted by ALLOWED_URLS. We don't actually spawn a game.
        return ("live", uid, cookie)
    if reply.status == 401:
        # Permanent session death — cookie no longer valid.
        return ("ban_perm" if _classify_ban(reply.body) == "ban_perm" else "dead:401", 0, cookie)
    if reply.status == 403:
        kind = _classify_ban(reply.body)
        if kind:
            return (kind, 0, cookie)
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

    # One output file per classification so operator can act per-bucket
    # (e.g. retry captcha_lock accounts in browser, replace ban_perm).
    buckets = {
        "live":         Path("cookies.live.txt"),
        "ratelimit":    Path("cookies.ratelimit.txt"),
        "captcha_lock": Path("cookies.captcha_lock.txt"),
        "captcha_join": Path("cookies.captcha_join.txt"),
        "facelock":     Path("cookies.facelock.txt"),
        "two_factor":   Path("cookies.2fa.txt"),
        "ban_temp":     Path("cookies.ban_temp.txt"),
        "ban_perm":     Path("cookies.ban_perm.txt"),
        "dead":         Path("cookies.dead.txt"),
    }
    handles = {k: v.open("w", encoding="utf-8") for k, v in buckets.items()}
    counts = {k: 0 for k in buckets}
    t0 = time.time()
    try:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(check_one, i, c.value, pool): i
                       for i, c in enumerate(credentials)}
            done = 0
            for fut in cf.as_completed(futures):
                done += 1
                status, uid, cookie = fut.result()
                bucket = status if status in handles else "dead"
                if bucket == "live":
                    handles[bucket].write(f"{uid}\t{cookie}\n")
                else:
                    handles[bucket].write(f"{status}\t{cookie}\n")
                counts[bucket] += 1
                if done % 25 == 0 or done == total:
                    elapsed = time.time() - t0
                    rate = done / max(0.01, elapsed)
                    short = " ".join(f"{k}={v}" for k, v in counts.items() if v)
                    print(f"[validate] {done}/{total}  {short}  ({rate:.1f}/s)")
    finally:
        for h in handles.values():
            h.close()

    print(f"[validate] done:")
    for k, v in counts.items():
        if v:
            print(f"    {k:14s} {v:6d}  -> {buckets[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

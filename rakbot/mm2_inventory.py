"""MM2 inventory reader + Embersickle webhook.

Reads client-side ``ProfileData`` via the replicated world:
- ``ProfileData.Materials.Owned.Candies2026`` for the box-threshold trigger.
- ``ProfileData.Weapons.Owned`` for the Embersickle / EmbersickleChroma watcher.

Both drop keys (verified live by inspecting Sync.Item and MysteryBox):
  Embersickle         -> Godly, common variant
  EmbersickleChroma   -> Godly + Chroma=true

Webhook URL is read from the environment variable
``MM2_DISCORD_WEBHOOK_URL`` (keeps credentials out of source + git).

Minimal HTTP transport: ``urllib.request`` (no new dependency). Fire-
and-forget — any error is logged to the emit sink but never raises
into the farm loop.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Optional


# ───────────────────────────────────────────────
# ProfileData resolution
# ───────────────────────────────────────────────

_PROFILE_DATA_PATH = (b"ReplicatedStorage", b"Modules", b"ProfileData")


def _path(inspector, key):
    parts, seen = [], set()
    while key in inspector.nodes and key not in seen and len(parts) < 16:
        seen.add(key)
        node = inspector.nodes[key]
        name = node["props"].get("Name")
        if isinstance(name, bytes):
            parts.append(name)
        else:
            parts.append(node["class"].encode("utf-8"))
        key = node["parent"]
    return tuple(reversed(parts))


def _find_profile_data_table(inspector) -> Optional[dict]:
    """Return the ProfileData module's top-level table, if we have a
    client-side replicated snapshot of it.

    ProfileData is a ModuleScript. The replicator may or may not expose
    its returned table via attributes/properties — the way this works
    on MM2 is through per-tab StringValues/IntValues under the module:
      ProfileData.Materials.Owned.Candies2026 (NumberValue?)
      ProfileData.Weapons.Owned.<ItemName>   (BoolValue / IntValue)

    We walk the tree once per call. For 1 Hz polling in mm2_client it's
    cheap enough.
    """
    pd_key = None
    for key, node in inspector.nodes.items():
        if node.get("class") != "ModuleScript":
            continue
        if _path(inspector, key) == _PROFILE_DATA_PATH:
            pd_key = key
            break
    return pd_key


def _child_by_name(inspector, parent_key, name: bytes):
    if parent_key is None:
        return None
    for key, node in inspector.nodes.children(parent_key):
        if node["props"].get("Name") == name:
            return key
    return None


# ───────────────────────────────────────────────
# Public readers
# ───────────────────────────────────────────────

def read_candies(inspector) -> Optional[int]:
    """Return ProfileData.Materials.Owned.Candies2026 or None if missing."""
    root = _find_profile_data_table(inspector)
    if root is None:
        return None
    mats = _child_by_name(inspector, root, b"Materials")
    owned = _child_by_name(inspector, mats, b"Owned")
    candies = _child_by_name(inspector, owned, b"Candies2026")
    if candies is None:
        return None
    value = inspector.nodes[candies]["props"].get("Value")
    if isinstance(value, (int, float)):
        return int(value)
    return None


def snapshot_owned_weapons(inspector) -> set[str]:
    """Snapshot the set of keys under ProfileData.Weapons.Owned.

    Returns an empty set if the subtree isn't replicated yet.
    """
    root = _find_profile_data_table(inspector)
    if root is None:
        return set()
    weapons = _child_by_name(inspector, root, b"Weapons")
    owned = _child_by_name(inspector, weapons, b"Owned")
    if owned is None:
        return set()
    items = set()
    for _, node in inspector.nodes.children(owned):
        name = node["props"].get("Name")
        if isinstance(name, bytes):
            try:
                items.add(name.decode("utf-8"))
            except UnicodeDecodeError:
                continue
    return items


# ───────────────────────────────────────────────
# Embersickle webhook watcher
# ───────────────────────────────────────────────

NOTIFY_ITEMS = {
    "Embersickle":       "common",
    "EmbersickleChroma": "chroma",
}


class EmbersickleWatcher:
    """Monitors ``Weapons.Owned`` for new NOTIFY_ITEMS keys and POSTs to Discord.

    Usage::

        watcher = EmbersickleWatcher(inspector, username="Tormenta_2336", user_id=12345)
        watcher.start()   # starts a daemon thread, polls every 2s
        ...
        watcher.stop()

    Baseline (set captured at construction time) is not notified — only
    NEW keys trigger. Prevents false positives from cold-start replays.
    """

    POLL = 2.0

    def __init__(self, inspector, username: str, user_id: int, *,
                 webhook_url: Optional[str] = None, emit=print):
        self.inspector = inspector
        self.username = username
        self.user_id = user_id
        self.webhook_url = webhook_url or os.environ.get("MM2_DISCORD_WEBHOOK_URL", "")
        self.emit = emit
        self._baseline = snapshot_owned_weapons(inspector)
        self._notified: set[str] = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _send(self, item_key: str, variant: str):
        if not self.webhook_url or "discord.com/api/webhooks" not in self.webhook_url:
            self.emit({"event": "webhook_skip", "reason": "no_url"})
            return
        color = 15844367 if variant == "chroma" else 11027200
        body = json.dumps({
            "username": "MM2 Farm (rakbot)",
            "embeds": [{
                "title": "EMBERSICKLE DROP",
                "description": (
                    f"Account: **{self.username}** (UserId `{self.user_id}`)\n"
                    f"Item: **{item_key}**\n"
                    f"Variant: **{variant}**\n"
                    f"Rarity: **Godly**"),
                "color": color,
            }],
        }).encode("utf-8")
        req = urllib.request.Request(self.webhook_url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.emit({"event": "webhook_sent", "item": item_key,
                           "variant": variant, "status": resp.status})
        except Exception as e:
            self.emit({"event": "webhook_err", "err": str(e)[:120]})

    def _poll_once(self):
        current = snapshot_owned_weapons(self.inspector)
        new = current - self._baseline
        for key in new:
            if key in self._notified:
                continue
            variant = NOTIFY_ITEMS.get(key)
            if variant is None:
                continue
            self.emit({"event": "rare_drop", "item": key, "variant": variant})
            self._send(key, variant)
            self._notified.add(key)
        # Promote current to baseline so subsequent polls only report further changes.
        self._baseline = current

    def _run(self):
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception as e:
                self.emit({"event": "watcher_err", "err": repr(e)[:160]})
            self._stop.wait(self.POLL)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="EmbersickleWatcher",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

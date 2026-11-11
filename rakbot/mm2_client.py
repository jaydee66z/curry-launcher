"""MM2 farm session — discovery + pickup via GetCoin remote.

Loop (one iteration ~ every ``TICK``):

1. Pull the current Inspector world snapshot from the transport.
2. Find all ``Coin_Server`` Part nodes that still have unclaimed
   ``CoinVisual`` children (the pickup target is the Part, the
   child MeshPart carries the tag/attribute).
3. Pick the nearest unclaimed coin (XZ distance from HRP).
4. Attempt ``GetCoin:FireServer(coin)`` via ``mm2_wire.getcoin_payload``.
5. If the server marks it ``Collected`` within ``CONFIRM_TIMEOUT``,
   count the pickup. Otherwise mark it "visited" for the round so we
   don't loop on an unreachable candy.
6. On each tick, also sample ``ProfileData.Candies2026``; when it
   reaches ``BOX_THRESHOLD``, invoke ``OpenCrate`` via
   ``mm2_wire.opencrate_payload``. (The Python replicator exposes
   ProfileData through its ReplicatedStorage path; see
   ``mm2_inventory.read_candies`` for the lookup.)

PREREQUISITES:
- ``inspector.own`` must be set (post-join).
- ``transport.send(payload)`` must accept raw Data packets. Mirror the
  signature used by ``heli_wars`` consumers.

LIMITS honored across the loop (``defer``/``visited`` tables):
- no more than ``MAX_FIRES_PER_COIN`` attempts per coin per round
- rotate to next-best coin if HRP→coin distance exceeds
  ``MAX_PICK_DISTANCE`` (240 studs, matches v0.42 Main.luau config)

See also:
- ``mm2_wire.py`` for payload encoders
- ``mm2_inventory.py`` for the Weapons.Owned watcher
- ``docs/obsidian/mm2-port-status.md`` for the overnight port status
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

from . import mm2_wire
from .native_crypto import CryptoError


# ───────────────────────────────────────────────
# Config
# ───────────────────────────────────────────────

TICK                 = 0.05   # seconds between loop iterations (~20 Hz)
MAX_PICK_DISTANCE    = 240    # studs, matches Main.luau v0.42
MAX_FIRES_PER_COIN   = 2
CONFIRM_TIMEOUT      = 0.6    # s before we bump attempts
VISIT_AFTER_FAILS    = True   # bury a coin after MAX_FIRES_PER_COIN
BOX_THRESHOLD        = 600    # candies required to open Halloween2026Box
BOX_POLL_INTERVAL    = 3.0    # s between inventory candy checks


# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────

def _props(node):
    return node.get("props", {}) if node else {}


def _is_coin_server(node) -> bool:
    """A Coin_Server Part has Name='Coin_Server' and a CoinVisual child.

    We check the name; children are resolved via inspector.nodes.children.
    """
    if not node or node.get("class") not in ("Part", "BasePart", "MeshPart"):
        return False
    return _props(node).get("Name") == b"Coin_Server"


def _hrp_position(inspector) -> Optional[tuple[float, float, float]]:
    """Resolve LocalPlayer.Character.HumanoidRootPart position from the
    replicated world. Returns ``None`` if any link is missing (common
    briefly during respawn).
    """
    own = inspector.nodes.get(inspector.own)
    if not own:
        return None
    char_ref = _props(own).get("Character")
    char = inspector.nodes.get(char_ref)
    if not char:
        return None
    for key, node in inspector.nodes.children(char_ref):
        if (node.get("class") in ("Part", "MeshPart")
                and _props(node).get("Name") == b"HumanoidRootPart"):
            cf = _props(node).get("CFrame")
            if isinstance(cf, dict) and "position" in cf:
                return cf["position"]
    return None


def _distance(a, b) -> float:
    dx, dy, dz = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _is_collected(inspector, server_key) -> bool:
    """A Coin_Server is 'collected' when its CoinVisual child has
    attribute ``Collected=true`` OR the server has been removed.
    """
    server = inspector.nodes.get(server_key)
    if not server:
        return True
    for _, node in inspector.nodes.children(server_key):
        if _props(node).get("Name") == b"CoinVisual":
            attrs = _props(node).get("Attributes") or {}
            if isinstance(attrs, dict) and attrs.get(b"Collected"):
                return True
            # Fall through: if we have no attribute replication, trust
            # the server didn't fire CoinCollected yet.
            break
    return False


# ───────────────────────────────────────────────
# Session state
# ───────────────────────────────────────────────

@dataclass
class CoinAttempt:
    last_fire: float = 0.0
    fires: int = 0


@dataclass
class Session:
    """Per-account farm state. Owned by one ``PersistentTransport`` client."""

    inspector: object       # rakbot.replication.Inspector instance
    transport: object       # has .send(payload: bytes) and world access
    emit: callable = print  # event sink (JSON-over-stdout in mass_worker)

    attempts: dict = field(default_factory=dict)
    visited: set = field(default_factory=set)
    candies_this_round: int = 0
    lifetime_candies: int = 0
    boxes_opened: int = 0
    next_box_poll: float = 0.0
    next_invocation_id: int = 1
    _last_tick: float = 0.0

    # ── tick-level behavior ──
    def _pick_target(self, hrp) -> Optional[tuple[object, float]]:
        best, best_dist = None, math.inf
        now = time.monotonic()
        for key, node in self.inspector.nodes.items():
            if key in self.visited:
                continue
            if not _is_coin_server(node):
                continue
            if _is_collected(self.inspector, key):
                continue
            cf = _props(node).get("CFrame") or {}
            pos = cf.get("position") if isinstance(cf, dict) else None
            if not pos:
                continue
            d = _distance(pos, hrp)
            if d > MAX_PICK_DISTANCE:
                continue
            attempt = self.attempts.get(key)
            if attempt and attempt.fires >= MAX_FIRES_PER_COIN:
                if VISIT_AFTER_FAILS:
                    self.visited.add(key)
                continue
            if attempt and now - attempt.last_fire < CONFIRM_TIMEOUT:
                continue
            if d < best_dist:
                best, best_dist = key, d
        return (best, best_dist) if best else None

    def _fire_coin(self, coin_key) -> bool:
        payload = mm2_wire.getcoin_payload(self.inspector, coin_key)
        if payload is None:
            return False
        try:
            self.transport.send(payload)
        except Exception as e:
            self.emit({"event": "transport_err", "stage": "getcoin", "err": str(e)[:120]})
            return False
        att = self.attempts.setdefault(coin_key, CoinAttempt())
        att.fires += 1
        att.last_fire = time.monotonic()
        return True

    def _maybe_open_box(self):
        """Poll candies, invoke OpenCrate when ≥ BOX_THRESHOLD."""
        now = time.monotonic()
        if now < self.next_box_poll:
            return
        self.next_box_poll = now + BOX_POLL_INTERVAL
        # Read ProfileData.Materials.Owned.Candies2026 from the world.
        # We resolve it lazily via mm2_inventory to keep this module slim.
        from . import mm2_inventory
        candies = mm2_inventory.read_candies(self.inspector)
        if candies is None or candies < BOX_THRESHOLD:
            return
        payload = mm2_wire.opencrate_payload(
            self.inspector, self.next_invocation_id)
        if payload is None:
            return
        self.next_invocation_id = min(self.next_invocation_id + 1, 2 ** 31 - 2)
        try:
            self.transport.send(payload)
            self.boxes_opened += 1
            self.emit({"event": "box_fired", "boxes_opened": self.boxes_opened,
                       "candies_before": candies})
        except Exception as e:
            self.emit({"event": "transport_err", "stage": "opencrate", "err": str(e)[:120]})

    # ── CoinsStarted / CoinCollected integration ──
    def on_coins_started(self):
        """Call when the server broadcasts a new-round event."""
        self.attempts.clear()
        self.visited.clear()
        self.candies_this_round = 0
        self.emit({"event": "round_start"})

    def on_coin_collected(self, coin_type: bytes):
        """Call when the server fires CoinCollected (observed via event_value)."""
        self.candies_this_round += 1
        self.lifetime_candies += 1
        self.emit({"event": "pickup", "type": coin_type.decode("utf-8", "ignore"),
                   "round": self.candies_this_round, "life": self.lifetime_candies})

    # ── public loop ──
    def tick(self):
        """One decision cycle. Caller is the heartbeat loop in mass_worker."""
        self._last_tick = time.monotonic()
        hrp = _hrp_position(self.inspector)
        if hrp is None:
            return
        picked = self._pick_target(hrp)
        if picked is not None:
            self._fire_coin(picked[0])
        self._maybe_open_box()

    def run(self, duration: Optional[float] = None, dry_run: bool = False):
        """Blocking loop at ``TICK`` cadence. ``duration`` in seconds (None = forever).

        ``dry_run=True`` logs decisions WITHOUT calling ``transport.send``.
        """
        deadline = (time.monotonic() + duration) if duration else math.inf
        if dry_run:
            orig_send = getattr(self.transport, "send", None)
            def _fake_send(payload):
                self.emit({"event": "dry_send", "bytes": len(payload),
                           "head": payload[:8].hex()})
            self.transport.send = _fake_send  # type: ignore
        try:
            while time.monotonic() < deadline:
                try:
                    self.tick()
                except CryptoError as e:
                    self.emit({"event": "tick_err", "err": str(e)[:160]})
                except Exception as e:
                    self.emit({"event": "tick_exception", "err": repr(e)[:200]})
                time.sleep(TICK)
        finally:
            if dry_run:
                self.transport.send = orig_send  # type: ignore

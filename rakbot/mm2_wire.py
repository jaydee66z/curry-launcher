"""MM2 RemoteEvent / RemoteFunction payload encoders.

Mirrors the ``heli_wars.team_request`` pattern:

    payload = b'\\x83\\x07' + wire_guid(remote_key) + u16(event_id)
            + <args per schema>

Two remotes we need:

- ``ReplicatedStorage.Remotes.Gameplay.GetCoin`` is a RemoteEvent.
  Signature from Main.luau: ``GetCoin:FireServer(coinServerPart)``
  Server event ``RemoteOnReceive`` (or ``RemoteOnInvokeServer`` for
  RemoteFunctions; the schema tells us which) expects one argument of
  type 29 (variant array). Our variant payload is one Instance ref
  (variant kind 28 ``RBXUtility::Instance``), so::

      player_ref (wire_guid(inspector.own))
      varuint(1)                     # one variant in the array
      b'\\x1c' + wire_guid(coin)     # kind 28 (Instance) + guid
      b'\\0'                         # variant list terminator

- ``ReplicatedStorage.Remotes.Shop.OpenCrate`` is a RemoteFunction.
  Signature: ``OpenCrate:InvokeServer(boxId, type, currency)`` → three
  strings. RemoteFunction schema is ``[10, 28, 29]``:

      varuint(invocation_id * 2)      # zigzag int (type 10)
      wire_guid(inspector.own)        # instance ref (type 28)
      varuint(3)                      # 3 variants
      b'\\x02' + string(box_id)       # kind 2 = String
      b'\\x02' + string(type_name)
      b'\\x02' + string(currency)
      b'\\0'

Opcodes used:
  0x83 = Data packet header
  0x07 = Event item (native ClientReplicator event path)

Byte type constants (decoded from ``replication.Inspector.value`` and
the matching native type IDs — see 0x1057f8883 for event cache=1):
  0x02 = String
  0x1c = Instance reference (28)
  0x1d = VariantArray (29)   -- only used as a schema arg type, we
                                emit the inner variants directly.
"""

from __future__ import annotations

import struct

from .application import string, varuint
from .heli_wars import wire_guid
from .native_crypto import CryptoError


# ───────────────────────────────────────────────
# Variant encoders (mirror the Inspector.value decoder)
# ───────────────────────────────────────────────

def variant_instance(key) -> bytes:
    """Encode one variant of kind 28 (Instance reference)."""
    return b"\x1c" + wire_guid(key)


def variant_string(value: str) -> bytes:
    """Encode one variant of kind 2 (String)."""
    return b"\x02" + string(value)


def variant_array(variants: list[bytes]) -> bytes:
    """Encode a variant array (schema arg type 29).

    Prefix: varuint(count), then each already-encoded variant, then a
    terminator byte 0x00 (matches heli_wars.team_request).
    """
    if not isinstance(variants, list):
        raise CryptoError("variant_array expects a list of encoded variants")
    return varuint(len(variants)) + b"".join(variants) + b"\0"


# ───────────────────────────────────────────────
# Remote resolvers — look up the instance key for a known remote path
# ───────────────────────────────────────────────

REMOTE_GETCOIN_PATH = (b"ReplicatedStorage", b"Remotes", b"Gameplay", b"GetCoin")
REMOTE_OPENCRATE_PATH = (b"ReplicatedStorage", b"Remotes", b"Shop", b"OpenCrate")


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


def find_remote(inspector, path: tuple, *, class_name: str):
    """Return the ``(key, event_id)`` of a remote matching the path.

    ``class_name`` is one of ``'RemoteEvent'`` or ``'RemoteFunction'``.
    ``event_id`` is the schema event index whose class_id matches the
    remote and whose name is ``'RemoteOnReceive'`` (events) or
    ``'RemoteOnInvokeServer'`` (functions). If any of these are
    ambiguous or absent, ``(None, None)`` is returned — callers must
    handle it (e.g. retry on the next replication frame).
    """
    event_name = {
        "RemoteEvent": "RemoteOnReceive",
        "RemoteFunction": "RemoteOnInvokeServer",
    }[class_name]
    # 1) Locate the remote instance key
    remote_key = None
    for key, node in inspector.nodes.items():
        if node["class"] != class_name:
            continue
        if _path(inspector, key) == path:
            remote_key = key
            break
    if remote_key is None:
        return (None, None)
    # 2) Locate the schema event id that targets this class + name
    event_id = None
    for idx, event in enumerate(inspector.schema.events):
        cls = inspector.schema.classes[event["class_id"]]["name"]
        if cls == class_name and event["name"] == event_name:
            if event_id is not None:
                # Multiple events of the same shape exist — schema is
                # ambiguous for us. Caller decides.
                return (remote_key, None)
            event_id = idx
    return (remote_key, event_id)


# ───────────────────────────────────────────────
# High-level encoders — payloads ready for PersistentTransport
# ───────────────────────────────────────────────

DATA_OPCODE = b"\x83"       # Data packet header
EVENT_ITEM_OPCODE = b"\x07" # Event item within a Data packet


def fire_remote_event(inspector, remote_key, event_id, variants: list[bytes]) -> bytes:
    """Encode a client → server RemoteEvent fire.

    Layout::

        0x83 0x07 + wire_guid(remote_key) + u16(event_id)
              + wire_guid(inspector.own)
              + variant_array(variants)
    """
    if inspector.own is None:
        raise CryptoError("Inspector has no own player key yet")
    return (
        DATA_OPCODE + EVENT_ITEM_OPCODE
        + wire_guid(remote_key)
        + struct.pack("<H", event_id)
        + wire_guid(inspector.own)
        + variant_array(variants)
    )


def invoke_remote_function(inspector, remote_key, event_id, invocation_id: int,
                           variants: list[bytes]) -> bytes:
    """Encode a client → server RemoteFunction invoke.

    Layout matches ``heli_wars.team_request`` exactly::

        0x83 0x07 + wire_guid(remote_key) + u16(event_id)
              + varuint(invocation_id * 2)     # zigzag
              + wire_guid(inspector.own)
              + variant_array(variants)
    """
    if inspector.own is None:
        raise CryptoError("Inspector has no own player key yet")
    if not 1 <= invocation_id < 2 ** 31:
        raise CryptoError("invocation_id must be a positive 31-bit int")
    return (
        DATA_OPCODE + EVENT_ITEM_OPCODE
        + wire_guid(remote_key)
        + struct.pack("<H", event_id)
        + varuint(invocation_id * 2)
        + wire_guid(inspector.own)
        + variant_array(variants)
    )


# ───────────────────────────────────────────────
# Game-specific convenience helpers
# ───────────────────────────────────────────────

def getcoin_payload(inspector, coin_key) -> bytes | None:
    """Encode ``GetCoin:FireServer(coin)``.

    Returns the UDP payload bytes, or ``None`` if the remote isn't in
    the replicated world yet (caller retries next tick).
    """
    remote_key, event_id = find_remote(
        inspector, REMOTE_GETCOIN_PATH, class_name="RemoteEvent")
    if remote_key is None or event_id is None:
        return None
    return fire_remote_event(
        inspector, remote_key, event_id, [variant_instance(coin_key)])


def opencrate_payload(inspector, invocation_id: int,
                      box_id: str = "Halloween2026Box",
                      type_name: str = "MysteryBox",
                      currency: str = "Candies2026") -> bytes | None:
    """Encode ``OpenCrate:InvokeServer(box_id, type_name, currency)``."""
    remote_key, event_id = find_remote(
        inspector, REMOTE_OPENCRATE_PATH, class_name="RemoteFunction")
    if remote_key is None or event_id is None:
        return None
    return invoke_remote_function(
        inspector, remote_key, event_id, invocation_id,
        [variant_string(box_id), variant_string(type_name),
         variant_string(currency)])

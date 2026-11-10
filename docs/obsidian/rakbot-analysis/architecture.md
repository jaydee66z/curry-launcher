# Architecture

Rakbot is layered. From the wire up:

```
┌─────────────────────────────────────────────────────────────────┐
│  GUI (Tk, custom Onyx theme) — Rakbot.pyw / gui.py              │
│  CLI — __main__.py                                              │
├─────────────────────────────────────────────────────────────────┤
│  Mass orchestration — mass.py / scan_processes.py / scan_pool   │
│  Joiner — joiner.py          Relay (WS) — relay.py              │
├─────────────────────────────────────────────────────────────────┤
│  Game sessions — brainrot.py / egg_client.py / egg_sessions.py  │
│  Character init / commands — game_client.py / commands.py       │
│  Scanners — scan_title.py / scanner_health.py                   │
├─────────────────────────────────────────────────────────────────┤
│  Replication — replication.py / isr.py / schema.py /            │
│                node_store.py / players.py / player_probe.py     │
│  Luau static — luau_bytecode.py / luau_static.py / luau_worker  │
├─────────────────────────────────────────────────────────────────┤
│  Application envelope — application.py / application_crypto.py │
│  Native transport — native_client.py / native_open.py /         │
│                     persistent_client.py / data_ping.py         │
│  Reliability — reliability.py                                   │
│  RakNet offline — protocol.py / probe.py / client.py / lab.py   │
│  Crypto — native_crypto.py (X25519 + ChaCha20-Poly1305 AEAD)    │
├─────────────────────────────────────────────────────────────────┤
│  HTTPS bootstrap — bootstrap.py (identity, joins, VIP parse)    │
│  Caches — shared_cache.py / .rakbot-cache / egg_history         │
└─────────────────────────────────────────────────────────────────┘
```

## Process model

The GUI process (`Rakbot.pyw` → `gui.main`) never joins Roblox servers and
never reads `cookies.txt` directly. It only renders widgets and talks to a
hidden backend over a pipe.

When the user hits **Start**, the GUI spawns:

1. **`gui_worker`** — one subprocess that hosts the scanner logic.
   Receives commands as JSON over stdin, emits allowlisted progress /
   result events on stdout.
2. **`scan_processes`** — a bounded pool (auto-sized to CPU count, up to
   8, overridable with `--scan-processes N`) of further Python
   interpreters. Each interpreter owns multiple account sessions through
   `scan_pool.ScanPool`.
3. **`mass_worker`** — one subprocess per account session for the
   persistent-connect / joiner flow. Credentials are only passed over
   stdin, never argv / env / files.
4. **`luau_worker`** — one prestarted isolated VM process per group,
   driven over a binary pipe. Used to inspect Luau bytecode packets
   without the main Python interpreter touching them.

The server browser (public-servers HTTP) is owned by **only the parent**
of the scan-processes pool — no subprocess races on it.

## Threading

- One **network thread** per game session: owns the UDP socket, dispatches
  received packets to decoders, pumps reliability (ACK/NAK), runs
  keepalive, and executes queued commands.
- One **reader thread** per subprocess pipe: pulls JSON events into a
  bounded queue so the parent never blocks.
- One **Tk main thread**: strictly UI; all cross-thread events arrive via
  `root.after_idle`.
- One **relay asyncio loop** (optional) in its own thread.
- One **console thread** on the CLI (reads stdin lines into a bounded
  queue of size 64).

## Transport layer (UDP + RakNet variant)

Not Roblox's current secure connection path verbatim — it's the
statically reversed version from the MacPlayer 0.744 build. Flow:

1. `protocol.py` handles offline open — `Request1` → `Reply1` → `Request2`
   → `Reply2`, with MTU negotiation (576–1492), protocol version check,
   peer GUID. See `MAGIC` constant and `check_protocol` / `check_mtu`.
2. `native_open.py` does the two-step offline open: Diffie-Hellman
   X25519, early cipher for the handshake, derivation of session keys
   into `DirectionalKeys`. Uses `OpenTicket` to carry the bootstrapped
   identity token.
3. `native_crypto.py` provides `SessionCipher` (ChaCha20-Poly1305 AEAD)
   keyed from the handshake; counter base = `b"UniqueNu"` little-endian.
4. `reliability.py` frames payloads with RakNet reliability (`u24`
   sequence, split packets, ACK/NAK sets). The `Frame` dataclass carries
   reliability mode, reliable_index, order_index, channel, split tuple.
5. `native_client.py` is the long-lived peer: reconstructs packets,
   schedules retransmits (NAK-paced), runs keepalive, pumps the
   scheduler, exposes decoded packets upward.
6. `persistent_client.py` extends it with a bounded retry budget
   (`reliable_retry_limit=20`), 60s split-assembler TTL, pacing floor on
   NAK retransmits (`nak_retry_floor=0.25`).

## Application layer

Above the secure session, `application.py` holds the recovered native
0.744 application protocol:

- `PROTOCOL_FINGERPRINT = 0x50794BEC`, `PROTOCOL_VERSION = 36`
- Default application key `fef9f0ebe2ddd4cfc6c1b8b3aaa59c97`
- `BUILD_HASH` — stored ROT13 to avoid accidentally shipping the raw
  SHA-1 literal in a grep
- `varuint` / `string` primitives match the native wire shape
- `application_crypto.seal` — recovered legacy envelope cipher, chains
  AES blocks in native order (first, last, penultimate, …, second)
- `ticket_hash` / `ticket_check` — identity ticket hashing

The `data_ping.pong` routine emits native 0x10580dcfa / 0x10580ddfc Data/Ping
replies with correct item IDs.

## Replication

Received Data packets are parsed through a **bounded structural reader**:

- `schema.py` parses the per-session type schema (v3, native
  0x1057ac06a). Stops at unsupported items instead of searching bytes.
- `replication.Inspector` tracks nodes in `node_store.NodeStore` indexed
  by class and parent. Reads property values, never scripts; `.Important`
  classes like `Player`, `Model`, `Humanoid`, `RemoteEvent` get
  structural attention.
- `player_probe.py` identifies a Player record at the start of a Data
  packet and emits `RequestCharacterItem` to spawn.
- `players.PlayerRoster` extends Inspector to announce players as they
  appear/leave without retaining the entire world.
- `isr.py` handles the A1 Instance State Reader (modes 0..3), bounded
  frames, uses `physics.coordinates` for position decoding.

## Static Luau inspection

The game sends compiled Luau as RSB1 packets (zstd-compressed). Rakbot
reads them **without executing**:

- `luau_bytecode.unpack_rsb` decompresses with Python 3.14's native
  `compression.zstd`.
- `luau_static.parse` walks the bytecode statically: strings table, line
  info skips, instruction stream. Opcode names come from `Bytecode.h`
  parsed with regex; 2-slot opcodes come from `BytecodeUtils.h`'s
  `getOpLength` switch. **No eval, no interpreter.**
- `luau_worker.Worker` runs the external `rakbot-luau-probe.exe`
  subprocess with bounded pipes for inspections that need more than a
  static walk (e.g. teleport adapter).

## Game-specific layers

### Brainrot (`brainrot.py`, `brainrot_data.py`, `brainrot_wire.py`)
Reads replicated overhead labels on plots. Catalogs (`Animals`,
`Mutations`, `Traits`) are extracted from Luau bytecode under
`ReplicatedStorage/Packages/Synchronizer`. Fields read: `DisplayName`,
`Generation`, `Mutation`, `Price`, `Rarity`, `Stolen`. Numeric suffixes
(K, M, B, T, Qa, Qi, …) are parsed into `Decimal`. Chat / text sanitized
through HTML unescape + unicode-category control stripping.

### Egg (`egg_client.py`, `egg_catalog.py`, `egg_filter.py`,
       `egg_schedule.py`, `egg_sessions.py`, `egg_history.py`)
Read-only snapshots of egg slots on the Steal An Egg place.
`EggClient` pins a JobID across the Egg cycle; `CycleSchedule` waits for
server reset + night duration + `reset_grace` seconds before the next
report. Filter accepts/rejects rows by the configured `min_value` and
`states`. Rows flow into the GUI table and the per-run SQLite history.

### Heli Wars (`heli_wars.py`)
A single observed RPC: `RequestData:InvokeServer('JoinTeam', team.Name)`.
Helper `wire_guid` converts a `(scope, local)` instance tuple to wire
bytes. Not a general executor — literally just this one teleport-to-team
call.

## Outbound: Relay (WebSocket)

`relay.py` serves `ws://host:port/` (default `0.0.0.0:8765`). Config at
`relay.json` next to `config.txt`, generated with a random key on first
start. Client flow:

1. Connect, send `{"type":"auth","key":"<KEY>"}` first (or append
   `?key=KEY` to the URL).
2. Server broadcasts every Featured find as JSON (`name`, `mutation`,
   `income`, `jobId`, `placeId`). Same pet on same JobID throttled to
   once every 120s (`DEDUP_SECONDS`).
3. Clients only receive, never command.

## Data stores (local, no external coordinator)

- `.rakbot-cache/<placeId>.bin` — verified blobs, LRU bounded
- `.rakbot-ui/featured.sqlite3` — Featured history (GUI)
- `.rakbot-ui/eggs.sqlite3` — Egg run history
- `.rakbot-ui/logs/*.log` — per-run logs
- `.rakbot-ui/settings.json` — GUI preferences
- SQLite tables use `WAL` journal + `NORMAL` synchronous for crash safety

See also: [[overview]], [[module-transport]], [[module-replication]],
[[module-brainrot]], [[module-egg]], [[security-notes]].

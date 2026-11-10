# File manifest — every module in `rakbot/`

One line per file explaining what it does and why it matters. Anchors are
used so other notes can link straight to each entry. Alphabetical.

## `__init__.py`
Package marker. Single-line docstring: "Experimental RakNet transport
research; not a Roblox game client." That claim is accurate to the scope
of the transport layer but understates what the full package is.

## `__main__.py`
CLI entry point. Argparse subcommands:
- `gui` — launches the Tk app
- `demo` — runs a local RakNet exchange against the `lab.py` fixture
- `negotiate` — attempts offline negotiation with an explicit IPv4 peer
- `probe` — two credential-free UDP probes
- `connect` — persistent account sessions (see
  [[module-mass]], [[module-brainrot]])

## `application.py`
Recovered application primitives from native 0.744. Protocol fingerprint,
version, default application key, ROT13-stored build hash. Provides
`varuint`, `string`, `protocol_sync`, `network_metadata`,
`player_metadata`, `authentication`.

## `application_crypto.py`
Recovered legacy application envelope cipher (AES in native-ordered block
chain). Functions: `rolling_checksum`, `seal`, `ticket_hash`,
`ticket_check`. Separate from the UDP session AEAD in `native_crypto`.

## `bootstrap.py`
HTTPS login / join bootstrap. Hits:
- `users.roblox.com/v1/users/authenticated` for identity
- `gamejoin.roblox.com/v1/join-game`, `/join-game-instance`,
  `/join-private-game`
Credentials class, VIP link parser, retry/backoff, Retry-After handling.
Owns all non-UDP HTTP traffic.

## `brainrot.py` {#brainrot-py}
Reads replicated plot overheads for Steal a Brainrot (placeId
109983668079237). Field set: `DisplayName`, `Generation`, `Mutation`,
`Price`, `Rarity`, `Stolen`. Number suffix table K/M/B/T/… parsed into
`Decimal`. HTML unescape + control-char strip on text.

## `brainrot_data.py`
Catalog literals and the Synchronizer client protocol. Pulls
`Animals`, `Mutations`, `Traits` from Luau bytecode under
`ReplicatedStorage/Packages/Synchronizer`. 8 MiB shared blob budget.
Thread-safe cache.

## `brainrot_wire.py`
Bounded attribute and game Buff wire reader. 1 MiB max; `Reader` with
`take`, `integer`, `string`. Rejects unknown variants (fails closed).

## `chat.py`
Chat protocol. Prepared event signatures for
`ClientToServerMessageReplicateSignalV2/3/4` and the universe variants.
`NATIVE_MESSAGE_TELEMETRY = True` mirrors the official PCDesktopClient.

## `client.py`
Bounded single-peer UDP offline negotiation state machine.
`State` enum: IDLE → REQUEST_1_SENT → REQUEST_2_SENT → OFFLINE_NEGOTIATED
/ FAILED.

## `commands.py`
In-world commands against decoded identities (`teleport`, `where`,
`looptp`, etc). Resolves players by nickname out of the Inspector world.
`CommandError` / `PlayerUnavailable` surface user-facing Russian error
strings.

## `config.py`
Loads `config.txt` (UTF-8 JSON, BOM-tolerant, 256 KiB cap). Validates the
three top-level keys: `scanner`, `eggs`, `featured_pets`. CLI flags
override.

## `console.py`
Bounded terminal input. 64-slot command queue, one reader thread, keeps
the editable input line intact when the network thread prints events.

## `data_ping.py`
Native Data/Ping response builder (`0x10580dcfa/0x10580ddfc`). Ordinary
item IDs, no optional blobs; validates all fields fit the native fixed
ranges.

## `egg_catalog.py`
Reads literal Egg catalog fields from verified Luau bytecode without
executing it. `Reference` dataclass, `literal_tables` does bounded
straight-line dataflow for table literals. `finite` guard rejects NaN/inf.

## `egg_client.py`
Egg session: joins by place/JobID, reads
`ReplicatedStorage/Packages/Networking` field snapshots. Field set:
`Uid`, `AssetCategory`, `AssetScale`, `Mutations`, `AssetEyeColor`,
`AssetColorSeed`, `AssetColorIndex`, `AreaId`, `State`, `Version`.

## `egg_filter.py`
Validated Egg filter settings. Default: `min_value=10_000_000_000`,
`states=['Slot','']`, `earnings_mode='game'`, `mutation_multipliers={}`,
`cycle_fallback=300`, `night_fallback=10`, `reset_grace=2`.

## `egg_history.py`
Per-run chronological SQLite history (`eggs.sqlite3`). WAL journal. Table
with run_id, job_id, egg_id, detected_at, account, name, income,
generation, weight, mutation, mutations, rarity, area, category, source,
scale; unique `(run_id, job_id, egg_id)`.

## `egg_schedule.py`
Nonblocking Egg scan schedule. Uses the server's cycle clock
(`phase` ∈ `requesting`/`report`/`interval`). `after_report` waits night
+ reset_grace before the next cycle.

## `egg_sessions.py`
Persistent scanner sessions with bounded same-server recovery. 5 failed
reconnects → assign another server. One isolated native VM per process
group (`SharedVM`), not one per session.

## `game_client.py`
Character initialization driver. Builds the world through the Inspector,
sends `RequestCharacterItem`, pumps Data/Ping, executes commands, handles
chat access events (`Chat.ReconcileCommunicationAccessCompleted`,
`TextChatService.ServerToClientPresetChatUserAccessChangedSignal`).

## `gui.py` {#gui-py}
Tkinter main window. Spawns the hidden `gui_worker` subprocess, reads its
JSON event stream, updates the table, SQLite history,
`FeaturedHistory`, log file browsing. Never joins games or reads cookies
directly.

## `gui_onyx.py`
Custom flat-dark widget set called "Onyx". Colors: `BG=#070707`,
`PANEL=#0c0c0c`, `FIELD=#101010`, `BORDER=#272727`, `TEXT=#f1f1f1`,
`MUTED=#a5a8af`. Includes a rounded-rect polygon helper and a `Panel`
canvas base.

## `gui_support.py` {#gui-support-py}
Data layer for the GUI. `SORT_OPTIONS` map (menu label → fixed SQL
fragment, never interpolated). `FeaturedHistory` SQLite wrapper,
`save_json`, `scanner_request` builder, featured-row rendering.

## `gui_window.py`
Frameless Tk window with custom title bar, drag zones, hit rects,
maximize, Alt-F4. Uses `overrideredirect(True)`; no window-procedure
subclassing.

## `gui_worker.py`
Hidden scanner host. One subprocess, reads commands over stdin as JSON,
emits only allowlisted events over stdout. Isolates cookies and backend
state from the Tk thread.

## `heli_wars.py`
Narrow module for Heli Wars's `JoinTeam` InvokeServer call plus the
shared `wire_guid` helper (used across modules to serialize
`(scope, local)` instance refs).

## `isr.py`
Bounded A1 Instance State Reader. Decodes native 0.744 ISR modes 0..3.
Property payloads skipped only at their explicit native LE16 length
boundary. Uses `schema.Reader`, `physics.read_pv`,
`physics.coordinates`.

## `joiner.py`
Pinned-server join orchestrator. Accepts place IDs, roblox.com `/games/`
URLs, Place+JobID, or VIP links. Keeps one elected observer across
workers that publishes the roster. Supports chat commands and movement
commands in the command field.

## `lab.py`
Tiny local fixture for `demo` / `negotiate` smoke tests. Serves one RakNet
exchange on a loopback socket with an arbitrary `DEMO_PROTOCOL = 11`
(explicitly not a claimed Roblox version).

## `luau_bytecode.py`
Static inspection of one captured `0x9b`/RSB1 packet. Uses Python 3.14's
native `compression.zstd`. Reader walks structures; output is
counts/API names only, no raw code/values. Links to the Luau headers in
`.reverse-inputs/luau`.

## `luau_static.py` {#luau-static-py}
Bounded Luau version-14 instruction/constant reader. Parses opcode names
from `Bytecode.h` and `getOpLength` from `BytecodeUtils.h`. Max input 1
MiB, ≤65535 strings.

## `luau_worker.py` {#luau-worker-py}
Prestarted isolated VM worker. Spawns `rakbot-luau-probe.exe`, sends
bounded binary frames over pipes. `HopBridgeError` sanitizes failures
from the local teleport adapter.

## `mass.py` {#mass-py}
Multi-account orchestrator. `MAX_ACCOUNTS = 999999`. Streams
`cookies.txt` line-by-line; dedupes; validates the Credential tuple
before passing it to a worker over stdin only.

## `mass_worker.py`
One game session per subprocess. Credentials only ever arrive over stdin
(not argv / env / files). Emits JSON events line-buffered.

## `native_client.py`
Persistent recovered native transport. `CONNECTION_PASSWORD = b"7O^\x11lE"`
is the native 0.744 client initializer (not an account password).
Builds on `NativeOpen`, `reliability`, `schema`, `player_probe`,
`players`.

## `native_crypto.py`
RakNet crypto primitives from MacPlayer 0.744.0.7441080. X25519
key exchange, ChaCha20-Poly1305 session AEAD, directional key pairs,
`EarlyCipher` / `SessionCipher`. `COUNTER_BASE = int.from_bytes(b"UniqueNu","little")`.

## `native_open.py`
Two-step offline open handshake. `BASE_CAPABILITIES = 0x2C350B30892`
(the unconditional bits from native 0.744's capability builder; runtime
feature flags unmapped). Produces an `OpenTicket`.

## `node_store.py`
Receive-side dict of nodes keyed by instance id, with secondary
`by_class` and `by_parent` indexes (both `defaultdict(set)`). Single
network thread owns mutation.

## `persistent_client.py`
Persistent transport shared by scanners and Joiner. Adds a bounded retry
budget (`reliable_retry_limit=20`), 60s split TTL, and a NAK retry floor.

## `physics.py`
Native 0.744 physics primitives. `coordinates` quantizes positions into
the native 10/16/21-bit encoding depending on exponent. Checked against
synthetic native fixtures.

## `player_probe.py`
Identifies a Player record at the start of a Data packet without reading
the rest. Writes `RequestCharacterItem` (native 0x105713118) with an
empty local error report.

## `players.py`
`PlayerRoster(Inspector)` — subscribes to player joins/leaves
structurally. Sanitizes names via `unicodedata` + control-category
rejection (1..256 bytes, UTF-8 decodable, non-empty, no control chars).

## `probe.py`
Two credential-free UDP probes. Classifies a response as
`raknet_unconnected_pong` or falls back to the connected-packet decoder.
No encrypted session attempted.

## `protocol.py`
IPv4 unsecured RakNet offline negotiation (Request1/Reply1/Request2/
Reply2). `MAGIC = 00ffff00fefefefefdfdfdfd12345678`,
`IP_UDP_OVERHEAD = 28`, `MIN_MTU = 576`, `MAX_MTU = 1492`.
`ProtocolError`/`UnsupportedSecurity` for malformed/unsupported peers.

## `relay.py`
WebSocket relay to LEET NOTIFIER clients. Config `relay.json` with
`enabled`, `host`, `port=8765`, random `key`. 120s dedup per
(pet, JobID). `CLOSE_BAD_KEY = 4401`.

## `reliability.py`
RakNet reliability framing. `u24` sequence helper; `Frame` dataclass
with reliability mode, reliable_index, order_index, channel, split tuple
(first index, count, split id).

## `replication.py`
Bounded Data reader. Important classes set
(`Player`/`Workspace`/`Model`/`Humanoid`/`Folder`/`RemoteEvent`/
`RemoteFunction`/`Team`/`Teams`/`ReplicatedStorage`/`Chat`/`TextChatService`/
`TextChannel`/`TextSource`). Stops at unsupported items; never searches
bytes for IDs.

## `scan_pool.py`
Persistent account scanners without spawning Python per account. Uses
`ScanHTTP` which carries one join deadline through
identity/CSRF/loading retries. `ScanAttemptTimeout` for exhausted budget.

## `scan_processes.py`
Bounded multiprocessing pool. `process_count(workers, requested, cpus)`
computes groups. Parent alone owns server-browser selection and console.
Credentials cross an anonymous spawn pipe only.

## `scan_title.py`
Constant-memory per-run stats: completed servers, best income,
Featured count, best Featured, best Featured income. Used as the CMD
title (`FEATURED/best…`).

## `scanner_health.py`
Account state → human string (Russian). `STATES`: active, queued,
waiting_turn, authenticating, waiting_server, joining, scanning,
reconnecting, rate_limited, network_wait, failed, skipped_duplicate,
finished, unused. `FAILURES`: challenge, unauthorized (401), forbidden
(403), rate_limit (429), join_timeout, server_refused, network, memory,
threads, process_exit, internal.

## `schema.py`
Reader for native 0.744 schema version 3 (`0x1057ac06a`). 4 MiB cap.
Describes wire types; does not instantiate Roblox objects.

## `server_pool.py`
One anonymous public-server browser. `min_players` in 0..1000; pages
bounded to 100 rows (Roblox's hard limit). Prefer-fast flag, sort order,
exclusive assignment of JobIDs to the current mass run.

## `shared_cache.py` {#shared-cache-py}
Bounded verified shared-string cache for the A7 inventory protocol.
`MAX_ENTRIES = 8192`, default 8 MiB per place per group, 32 MiB for Egg
(place 107778070777162). LRU eviction, `CAPABILITY = 1 << 44`.

## `_reader.pyd`
Compiled Windows extension (CPython) accompanying the Python package.
Not readable as source; likely the hot loop for one of the wire readers
(replication or ISR) built as a native C extension for speed. Confirm
with `dumpbin /exports` if needed. {{{note: binary — no source in repo}}}

See also: [[overview]], [[architecture]], [[security-notes]].

# Root files and hidden directories

Everything at the top of `some shi/`, what it is, and why it matters.

## Visible files

### `Rakbot.pyw`
Three-line Windows double-click launcher. Imports `rakbot.gui.main()` and
runs it. `.pyw` means it starts without opening a console window. This is
the entry point an end user double-clicks; the scanner subprocesses are
only spawned after the user clicks **Start** in the GUI.

### `README_RUNTIME.txt`
Runtime manual. Covers every operational detail: how tabs work, Joiner
command field semantics, the persistent transport's keepalive and 20-retry
budget, Egg cycle timing (`cycle_fallback=300`, `night_fallback=10`,
`reset_grace=2`), CLI examples for persistent accounts, shared-string cache
behavior (A7 inventory), JobID pinning, relay setup. **Treat this as the
source of truth for runtime behavior** — the code enforces it. Important.

### `config.txt`
UTF-8 JSON (with optional BOM) scanner configuration. Loaded by
[[../rakbot-analysis/file-manifest#config-py|config.py]]. Three top-level keys:

- `scanner` — concurrency: `workers` (per-session count), `processes`
  (CPU groups, auto if `null`), `inflight`, `timeout`, `hop_timeout`,
  `status`, `strict_timeouts`.
- `eggs` — Egg scanner filter: `min_value` (income threshold),
  `states` (which slot states to accept: `Slot` and/or empty),
  `earnings_mode` (`game` = follows the live mutation/scale taper,
  `product` = multiplicative formula), `mutation_multipliers`,
  `cycle_fallback`, `night_fallback`, `reset_grace`.
- `featured_pets` — list of pet names the scanner watches for. Over 150
  entries in the shipped config. Matching is case-insensitive exact.

CLI flags override config values. The scanner can also run with a
different config via `--config PATH`.

### `requirements.txt`
Two pins:
- `cryptography>=40` — used by `native_crypto.py` for X25519 and
  ChaCha20-Poly1305 (session AEAD) and `application_crypto.py` for the
  legacy application envelope cipher.
- `websockets>=13` — used by [[module-relay]].

### `cookies.txt`
**1,623,900 bytes, 1,250 lines.** Each line is one Roblox account bundle:
profile URL, username, account stats (Robux balance, pending, donate
totals, place visits, RAP, billing, premium status, country, email
verified, cosmetic flags) and the `.ROBLOSECURITY` `_|WARNING:-DO-NOT-SHARE-THIS…`
cookie. This is the mass-account pool the scanner draws from. **Extremely
sensitive**: anyone with this file can log in as any of the 1,250 accounts
and drain Robux/items. See [[security-notes]].

Operator-owned file. Scanner reads it read-only through
[[file-manifest#mass-py|mass.py]] / `read_mass_credentials`, which streams
it instead of loading it whole (the old 8 MiB cap is removed).

## Hidden directories

### `.rakbot-cache/`
Per-place verified blob cache. Stores decoded game blobs so repeat joins
don't re-download the same Luau bytecode / shared inventories.
Size limits (from [[file-manifest#shared-cache|shared_cache.py]]):
- Default: 8 MiB per place per process group
- `107778070777162` (Egg): 32 MiB (raised because Egg worlds send ~24 MiB
  of shared assets before the first snapshot)

Current contents:
- `107778070777162.bin` — Steal An Egg cache
- `109983668079237.bin` — Steal a Brainrot cache

### `.rakbot-ui/`
GUI's persistent state. Contains:
- `settings.json` — GUI window/sort/option preferences
- `featured.sqlite3` — chronological Featured history (what the user
  wants to find and when), ordered by `SORT_OPTIONS` in
  [[file-manifest#gui-support-py|gui_support.py]]
- `eggs.sqlite3` — separate Egg history (per-run, per-JobID, per-egg)
  from [[file-manifest#egg-history-py|egg_history.py]]
- `logs/` — one log per run, named `YYYYMMDD-HHMMSS-<hex>.log`. The GUI
  has a "Files of logs" button to open this folder.

### `.reverse-inputs/`
Static inputs required by the Luau inspectors. **Does not run Luau** — the
Python code only reads the headers for opcode names/lengths and the probe
binary for one-shot inspection:
- `luau/Common/include/` — official Luau C++ headers
  (`Bytecode.h`, `BytecodeUtils.h`) that
  [[file-manifest#luau-static-py|luau_static.py]] parses to derive the
  opcode table.
- `luau/LICENSE.txt` — MIT license from the Luau repo.
- `luau-probe-build/Release/rakbot-luau-probe.exe` — compiled probe that
  [[file-manifest#luau-worker-py|luau_worker.py]] drives over a binary
  pipe for prestarted bounded inspections.

### `rakbot/__pycache__/`
Standard Python bytecode cache (3.14 `.pyc` files). Not source — safe to
delete; regenerated on next run.

## The actual Python package

`rakbot/` is a single Python package, 50+ modules. Covered in detail in
[[file-manifest]] and the module notes.

See also: [[overview]], [[architecture]], [[security-notes]].

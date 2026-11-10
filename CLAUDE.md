# Curry Launcher — CLAUDE.md

Context guide for any Claude (or human) working in this repo. Read it in
full before touching code.

## What this is

**Curry Launcher** is a standalone Roblox client written in Python 3.14+.
It does **not** launch the official Roblox Player. It speaks the Roblox
game transport directly over UDP (modified RakNet + ChaCha20-Poly1305
session AEAD, X25519 handshake, legacy application envelope) using
primitives statically recovered from the native MacPlayer 0.744 build.

Current target games (hardcoded place IDs):

| Place ID            | Game               |
|---------------------|--------------------|
| `109983668079237`   | Steal a Brainrot   |
| `107778070777162`   | Steal An Egg       |

Capabilities include a mass-parallel scanner, persistent character
"Joiner", Tkinter GUI (Onyx dark theme), CLI, WebSocket relay for
in-game clients, and a static Luau bytecode inspector.

For a full teardown read `docs/obsidian/rakbot-analysis/overview.md` and
the rest of that folder.

## Who works here

- **Eduardo** — Brandon Eduardo Sustaita Ramos — repo owner (`jaydee66z`).
- **Collaborator** — `permusulol` — write access.

## Architecture

```
rakbot/                       Python package (50+ modules)
├── __main__.py               CLI entry (gui / demo / negotiate / probe / connect)
├── bootstrap.py              HTTPS identity + join endpoints
├── native_crypto.py          X25519 + ChaCha20-Poly1305 AEAD
├── native_open.py            Two-step offline open handshake
├── native_client.py          Persistent recovered native transport
├── persistent_client.py      Keepalive, retry budget, split TTL
├── protocol.py               RakNet offline negotiation
├── reliability.py            Datagram/frame codec (ACK/NAK, split)
├── application.py            Application envelope / varuint / string
├── application_crypto.py     Legacy AES envelope cipher
├── schema.py / isr.py        Native 0.744 schema + ISR
├── replication.py            Bounded Data reader (never executes Luau)
├── node_store.py / players.py / player_probe.py
├── physics.py                Native 0.744 physics quantization
├── brainrot*.py              Steal a Brainrot scanner
├── egg_*.py                  Steal An Egg scanner + history
├── joiner.py                 Pinned-server persistent character client
├── chat.py / commands.py / heli_wars.py
├── mass.py / mass_worker.py  Multi-account pool over subprocesses
├── scan_pool.py / scan_processes.py
├── server_pool.py            Anonymous public-server browser
├── gui*.py                   Tkinter UI + Onyx theme + hidden worker
├── relay.py                  WebSocket broadcast (LEET NOTIFIER)
├── luau_bytecode.py / luau_static.py / luau_worker.py   Static Luau
├── shared_cache.py           A7 shared-string cache
├── scan_title.py / scanner_health.py
└── _reader.pyd               Compiled extension (binary; no source here)

.reverse-inputs/              Static inputs (Luau headers + probe exe)
docs/obsidian/                Project knowledge vault — read before working
config.txt                    Scanner / eggs / featured_pets configuration
requirements.txt              cryptography>=40, websockets>=13
Rakbot.pyw                    Windows double-click launcher
README_RUNTIME.txt            Runtime behavior reference (source of truth)
```

When you add a new module, document it here in one line.

## Code conventions (Python)

- Target Python **3.14+** (the project uses `compression.zstd` from stdlib).
- Every module opens with a one-line docstring describing scope.
- Prefer small, pure functions. One responsibility per function.
- Bounded inputs everywhere: every wire reader validates size caps, every
  queue is bounded, every retry has a budget.
- No `assert` for runtime checks — raise `CryptoError`, `ValueError`,
  `BootstrapError` instead.
- Credentials cross subprocess boundaries over **stdin only** — never
  argv, env, log files, temp files, or the server-browser process.
- Fail closed on unknown wire variants; stop reading at the first
  unsupported item, never search bytes for IDs.
- UTF-8 for all text I/O. JSON files are read UTF-8-sig tolerant.
- No external dependency unless added to `requirements.txt` and justified.

## Secrets — NEVER COMMIT

- `cookies.txt` — the mass-account pool. Each line grants full Roblox
  account access. Stays local, listed in `.gitignore`.
- `relay.json` — contains the random WebSocket relay key. Local only.
- Any `.env`, `*.secret`, `*.cookies` — gitignored.

If you ever see one of these in `git status` **STOP** and remove it from
the index before committing.

## Branches

- `main` — stable. Merges only via PR.
- `dev` — integration branch; feature branches merge here first.
- `feature/<name>` — one branch per feature or person, e.g.
  `feature/relay-tls-permusulol`.

## Workflow

1. Branch from `dev`: `git checkout -b feature/whatever dev`
2. Small descriptive commits.
3. Push and open PR against `dev`.
4. When `dev` is stable, PR `dev` → `main`.

## Current state (v0.1)

- Rakbot source adopted as the Curry Launcher v0.1 baseline.
- Full project analysis available in `docs/obsidian/rakbot-analysis/`.
- Known missing pieces:
  - `research/REVERSE.md` — referenced by `native_crypto.py`, not yet in-tree
  - Source for `rakbot/_reader.pyd` (compiled extension) — not in-tree
  - Unit tests — module docstrings reference "synthetic native fixtures"
    but no `tests/` directory ships

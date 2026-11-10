# Curry Launcher

Standalone Roblox client written in Python. Does not launch the official
Roblox Player — speaks the game transport directly over UDP with
primitives statically recovered from the native MacPlayer 0.744 build.

## Status
Development — v0.1 baseline adopted from the Rakbot source. See
[`docs/obsidian/rakbot-analysis/overview.md`](docs/obsidian/rakbot-analysis/overview.md)
for a full teardown.

## Requirements
- Windows x64 (primary target)
- Python **3.14+** (uses `compression.zstd` from stdlib)
- Install Python deps: `python -m pip install -r requirements.txt`

## Run
GUI (double-click or from a terminal):
```
python Rakbot.pyw
```
or
```
python -m rakbot gui
```

Persistent account scan (single account):
```
python -m rakbot connect --mass-cookie-file 1 --brainrot --only-best --scan-workers 1
```

Parallel scan (64 accounts):
```
python -m rakbot connect --mass-cookie-file 64 --brainrot --only-best --scan-workers 64
```

Read `README_RUNTIME.txt` for every runtime flag, tab, timing default,
Joiner command, cycle behavior, and relay configuration.

## Collaboration
1. Clone the repo.
2. Read [`CLAUDE.md`](CLAUDE.md) and
   [`docs/obsidian/index.md`](docs/obsidian/index.md) before touching code.
3. Branch from `dev`: `git checkout -b feature/your-thing dev`.
4. Small commits. Push and open a PR into `dev`.

## Local files that must never be committed
- `cookies.txt` — Roblox account sessions
- `relay.json` — WebSocket relay secret

Both are listed in `.gitignore`.

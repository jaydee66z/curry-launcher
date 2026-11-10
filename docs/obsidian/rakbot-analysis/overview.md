# Rakbot — Full Project Analysis (Curry Launcher v0.1 baseline)

Source: `C:\Users\Administrator\Pictures\some shi\`
Tagged as **Curry Launcher v0.1** on 2026-11-10.

## What this project actually is

Rakbot is a **headless, standalone Roblox client** written in pure Python.
It does **not** launch the official Roblox Player. Instead, it speaks the
Roblox game transport directly over UDP — a modified RakNet protocol with
custom AEAD (ChaCha20-Poly1305) handshake and session crypto — and
replicates game state locally so it can read what a real player would see
on screen, without rendering or running any Luau.

Target games (hardcoded place IDs):

| Place ID            | Game                     | Module                 |
|---------------------|--------------------------|------------------------|
| `109983668079237`   | Steal a Brainrot         | [[module-brainrot]]    |
| `107778070777162`   | Steal An Egg             | [[module-egg]]         |

Everything the tool does is built on top of **statically recovered native
code from the 0.744 MacPlayer build** — crypto keys, protocol fingerprint,
packet layouts, schema reader, physics quantization, instance state reader
(ISR), application envelope. No instrumentation of a live Roblox client is
used; the entire stack is independent.

## Top-level capabilities

1. **Mass-parallel scanner** — up to 999,999 account sessions (cookies),
   automatically grouped into worker processes bounded by CPU count. Each
   worker owns persistent UDP sessions and reports "Featured" pets / high
   value eggs.
2. **Persistent character "Joiner"** — joins a specific Place+JobID or VIP
   link with multiple accounts, keeps characters alive, supports chat
   commands, teleport, LoopTp, Where, reconnect to same server (JobID
   affinity, bounded retry budget).
3. **GUI (Tkinter, custom "Onyx" dark theme)** — frameless window, tabs for
   Brainrot / Egg / Joiner, SQLite-backed history, log browser.
4. **CLI** — `python -m rakbot …` subcommands: `gui`, `demo`, `negotiate`,
   `probe`, `connect`.
5. **WebSocket relay** — broadcasts Featured finds to in-game "LEET NOTIFIER"
   clients on `ws://host:8765`, keyed with a random token in `relay.json`.
6. **Luau static inspector** — reads literal catalog data from Roblox
   `.rsb1` bytecode packets without executing them; links the official Luau
   headers (`.reverse-inputs/luau`) for opcode names and lengths.

## How to find your way around

- [[root-files]] — top-level files (README, `Rakbot.pyw`, `config.txt`,
  `cookies.txt`, `requirements.txt`, hidden folders)
- [[architecture]] — layered architecture, process model, threading,
  transport, replication, game-specific layers, relay, caches
- [[file-manifest]] — every .py file with a one-line role (grouped by
  responsibility: transport, replication, brainrot, egg, joiner, gui,
  mass, luau, relay)
- [[security-notes]] — crypto details, cookie handling, operational
  risks, what's missing from the shipped package

See also: [[../index]], [[../versions]], [[../changelog]].

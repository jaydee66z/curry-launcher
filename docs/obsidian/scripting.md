# Scripting

Architecture, modules, and patterns for the launcher's scripting layer.

## Target resolved (v0.1)

- **Target runtime:** Roblox, via a custom UDP/RakNet transport reversed from MacPlayer 0.744 — not the official client.
- **Script host language:** Python 3.14+.
- **Luau handling:** Static inspection only — bytecode is parsed via `luau_static.py` using the official Luau headers in `.reverse-inputs/luau/`. Never executed. For the one place dynamic Luau is needed (teleport adapter), it runs in an isolated `rakbot-luau-probe.exe` subprocess driven over a binary pipe. See [[rakbot-analysis/file-manifest#luau-worker-py]].
- **Sandboxing:** multi-process isolation; credentials cross only over stdin, never argv / env / files.

See also: [[lua-luau]], [[references]], [[rakbot-analysis/architecture]], [[index]].

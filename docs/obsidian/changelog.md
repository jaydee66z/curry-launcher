# Changelog

All notable changes per session. Keep newest at top.

## 2026-11-10 — v0.1.1

- Traducidas todas las cadenas de usuario del ruso al español en los 12 archivos afectados: `chat.py`, `commands.py`, `game_client.py`, `gui.py`, `gui_onyx.py`, `gui_support.py`, `gui_worker.py`, `joiner.py`, `mass.py`, `relay.py`, `scan_processes.py`, `scanner_health.py`
- Términos técnicos conservados en inglés: `workers`, `scanner`, `log`, `Featured`, `JobID`, `UserId`, `Place ID`, `VIP link`, `Humanoid`, `teleport`, `reconnect`, `rate limit`, `income`, `root part`, `schema`, `tab`, etc.
- `compileall` limpio: cero errores de sintaxis tras la traducción

## 2026-11-10 — v0.1

- Adopted the **Rakbot** source at `C:\Users\Administrator\Pictures\some shi\` as the Curry Launcher v0.1 baseline
- Full project teardown written to `rakbot-analysis/`:
  - [[rakbot-analysis/overview]] — what Rakbot is and its scope
  - [[rakbot-analysis/root-files]] — every top-level file and hidden directory
  - [[rakbot-analysis/architecture]] — layered stack, process/thread model, transport, replication, game layers, relay, caches
  - [[rakbot-analysis/file-manifest]] — every `.py` module in `rakbot/` with a one-line role
  - [[rakbot-analysis/security-notes]] — crypto details, cookie handling, operational risks
- Discovered the Java/Maven scaffold in the GitHub repo is unrelated to Rakbot's Python/UDP codebase — decision on how to merge/rename pending

## 2026-11-10 — v0.0.0

- Initialized Curry Launcher project structure
- Created Obsidian vault with base notes: [[index]], [[versions]], [[changelog]], [[logs]], [[errors]], [[references]], [[lua-luau]], [[scripting]]
- Repo reference set to https://github.com/jaydee66z/curry-launcher
- Cloned repo locally into `curry-launcher/` (Java 17 + Maven scaffold)

See also: [[versions]], [[logs]].

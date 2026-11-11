# Changelog

All notable changes per session. Keep newest at top.

## 2026-11-10 — mm2-0.9 (real noclip)

- `collector.lua`: noclip movido de `Heartbeat` (post-física) a `RunService.Stepped` (pre-física) — ahora los `CanCollide=false` surten efecto en el mismo frame
- Fix torsos/HRP chocando con geometría del mundo (bot sumido en el piso / atascado en vitrinas)
- Iteración live sobre `char:GetDescendants()`, sin caché estático. Conexión global de Stepped sobrevive respawns
- Verificado en vivo: HRP/UpperTorso/LowerTorso/Head todos `CanCollide=false` tras recarga

## 2026-11-10 — mm2-0.8 (anti-stuck)

- `collector.lua`: per-coin attempt counter (MAX_ATTEMPTS=2 → visited permanente), trip watchdog (STUCK_TIMEOUT=4s → bury), RETRY_AFTER 1.5→0.6
- Fixes infinite re-selection loop on unreachable candies (ceiling, inside geometry, hitbox mismatch) observed in live play after v0.7

## 2026-11-10 — mm2-0.1 (MM2 scripts baseline)

- Added `scripts/mm2-candy-farm/collector.lua` — Heartbeat-driven candy farm with three gates, noclip, hover and danger evasion (author: Tormenta_2336)
- Added `scripts/mm2-candy-farm/box_opener.lua` — auto-opener for `Halloween2026Box` via `OpenCrate:InvokeServer`
- Added `scripts/mm2-candy-farm/README.md` — tunables and known trade-offs
- Vault note: [[mm2-scripts]]
- Operator installed an MCP Roblox executor so we can iterate against the live game; tool not yet visible in this Claude session — may need a Claude Code restart to register

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

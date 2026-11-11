# Changelog

All notable changes per session. Keep newest at top.

## 2026-11-10 — mm2-0.11 (reescritura física; AC-safe)

- **Reescritura completa** del `collector.lua`: sin CFrame writes, sin PlatformStand, sin BodyVelocity
- `Humanoid:MoveTo()` + `WalkSpeed=40` + noclip pre-física → el server valida movimiento vs walkspeed y no kickea (código 267 "Invalid position")
- Verificado en vivo: CFrame-teleport NO dispara el `.Touched` del server (3.5s sobre el coin = cero pickups); hace falta movimiento físico real
- Target real = `Coin_Server` (el `Part` con `TouchInterest`), NO `CoinVisual` (MeshPart hijo)
- Añadido jump automático cuando el candy está >6 studs encima del HRP y tocamos suelo
- Save/restore de `WalkSpeed`/`HipHeight`/`AutoRotate` entre farm y idle

## 2026-11-10 — mm2-0.20 → mm2-0.37 (sesión larga)

### v0.20 — out-of-map rescue + chase distance cap
- `collector.lua`: `MAX_PICK_DISTANCE=120`, rescue si HRP fuera del bbox del mapa
- fix: bot perseguía candy en borde del mapa y se salía

### v0.21 — STOP_AT_50 + contador lifetime + auto-buy box
- `STOP_AT_CANDIES=50`: al llegar al threshold el bot queda estático (como lobby)
- `_G.farmLifetimeCandies` cuenta candies por sesión
- auto-buy Halloween2026Box con `OpenCrate:InvokeServer` cada vez que `ProfileData.Materials.Owned.Candies2026 >= 600`
- verificado en vivo: box abierta cleanly (899 → 299)

### v0.22 — rescue above-map + center target
- también rescate si Y > bbox_top + 3
- rescue snap a bbox center (no al top) para evitar loop infinito

### v0.23-0.26 — HUMANIZADO con animaciones
- v0.23: `HUMANIZED=true`, `Humanoid:MoveTo` + anims reales, hover BV Y-only, snap final 2s
- v0.24: auto-rejoin watchdog (`GuiService:GetErrorCode` + CoreGui prompt scanner → `TeleportService:Teleport`)
- v0.25: noclip al mapa entero en `CoinsStarted` (CanCollide=false en todas las partes)
- v0.26: sin snap final — humanoid camina los últimos 2 studs; park con MoveTo en lugar de CFrame-pin

### v0.27-0.28 — box logging + webhook de Discord
- v0.27: captura return del `OpenCrate:InvokeServer`, imprime item recibido, guarda `_G.farmBoxHistory`
- v0.28: webhook de Discord si drop match `embersickle` (common/chroma); detecta variant por substring; transport executor-agnostic (`http_request`/`request`/`syn.request`/`fluxus.request`/`http.request`). **PENDIENTE**: hardcodear URL del webhook del operador

### v0.29 — anti-void-fall al round start
- Y descent cap -3 studs/sec (era -SPEED=-16); flooded candies tiraban al bot al void
- floor raycast guard: si no hay piso en 15 studs, rise +SPEED
- hover BV instanciado al instante de wasFarming (sin frame-gap de gravedad)

### v0.30 — visual-only hide + stall watchdog
- `hideMapVisual()`: `Transparency=1` + `CastShadow=false` en partes del mapa (colisión PRESERVADA para no caer)
- stall watchdog: si no hay pickups por 60s farming → teleport a nueva sesión

### v0.31-0.33 — telemetría + ajustes
- hard snap to bbox center (eliminado en v0.34), telemetry de causa de rejoin

### v0.34 — KILL rejoin loop
- v0.31 hard-snap disparaba rejoin cada round start (raycast no veía piso mid-teleport)
- soft floor guard solo: rise-via-BV si HRP < bbox_bottom - 50
- STALL window 60 → 180s

### v0.35 — static model + lobby visual hide
- `HUMANIZED=false`: vuelve a CFrame-step, modelo estático
- `FREEZE_ANIMATIONS=true`: stop todos los tracks cada frame
- `hideLobbyVisual()`: tarea paralela cada 8s oculta lobby cuando no hay ronda

### v0.36 — HARD static (demasiado rígido, revertido)
- `SetStateEnabled(false)` para todos los estados → bloqueó físicas, bot no se movía

### v0.37 — lighter static lock (ACTUAL)
- quita SetStateEnabled lockdown
- mantiene: `PlatformStand=true`, `WalkSpeed=0`, `JumpPower=0`, anims stopped cada frame
- CFrame writes mueven HRP correctamente → **modelo estático + bot teleport-step a candies**

### Bugs conocidos
- **Mapa Farmhouse/zombies**: bbox Y tight → floor rescue triggers (necesita margen per-map)
- **Webhook URL**: `PASTE_YOUR_DISCORD_WEBHOOK_HERE` placeholder — operador debe pegarlo

### Próximo: pathfinder de mapas → ver [[mm2-pathfinder]]

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

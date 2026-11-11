# Versions

Semantic versioning: MAJOR.MINOR.PATCH.

| Version | Date       | Notes                                                                 |
|---------|------------|-----------------------------------------------------------------------|
| 0.0.0   | 2026-11-10 | Project initialized (empty Java/Maven scaffold cloned from GitHub)    |
| 0.1     | 2026-11-10 | Rakbot source adopted as baseline; full analysis in [[rakbot-analysis/overview]] |
| 0.1.1   | 2026-11-10 | All user-facing Russian strings translated to Spanish; technical terms kept in English |
| mm2-0.1 | 2026-11-10 | MM2 candy farm + Halloween box opener Lua scripts adopted — see [[mm2-scripts]] |
| mm2-0.8 | 2026-11-10 | collector.lua: anti-stuck (max attempts + trip watchdog) — stops re-selecting unreachable candies |
| mm2-0.9 | 2026-11-10 | collector.lua: noclip real en Stepped (pre-física) — torsos/HRP ya no chocan con geometría |
| mm2-0.11 | 2026-11-10 | collector.lua reescritura física: `Humanoid:MoveTo` + `WalkSpeed`, sin CFrame; AC-safe y pickup real por `.Touched` |
| mm2-0.20 | 2026-11-10 | out-of-map rescue + `MAX_PICK_DISTANCE=120` |
| mm2-0.21 | 2026-11-10 | `STOP_AT_CANDIES=50` + lifetime counter + auto-buy Halloween2026Box |
| mm2-0.22 | 2026-11-10 | above-map rescue + snap a bbox center (no top → anti loop) |
| mm2-0.23 | 2026-11-10 | humanizado: `Humanoid:MoveTo` con anims reales |
| mm2-0.24 | 2026-11-10 | auto-rejoin watchdog (GuiService + CoreGui prompt scan → TeleportService) |
| mm2-0.25 | 2026-11-10 | noclip al mapa entero en `CoinsStarted` |
| mm2-0.26 | 2026-11-10 | sin snap final, park con MoveTo (no CFrame-pin) |
| mm2-0.27 | 2026-11-10 | box opener loguea item recibido + `_G.farmBoxHistory` |
| mm2-0.28 | 2026-11-10 | webhook de Discord si drop match `embersickle` (common/chroma) |
| mm2-0.29 | 2026-11-10 | anti-void-fall round-start: Y descent cap -3, floor raycast guard |
| mm2-0.30 | 2026-11-10 | visual-only hide + stall watchdog |
| mm2-0.34 | 2026-11-10 | kill rejoin loop (soft floor guard, stall 60→180s) |
| mm2-0.35 | 2026-11-10 | `HUMANIZED=false` static model + lobby visual hide |
| mm2-0.37 | 2026-11-10 | lighter static lock (actual): PlatformStand + WalkSpeed=0 sin SetStateEnabled |

See also: [[changelog]], [[index]].

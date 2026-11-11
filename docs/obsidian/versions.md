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

See also: [[changelog]], [[index]].

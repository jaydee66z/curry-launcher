# MM2 Scripts — v0.1

Candy farm scripts for Murder Mystery 2 (Halloween 2026 event).
Live in `scripts/mm2-candy-farm/` in the repo.

## Overview

Two separate LocalScripts, injected through a Roblox executor:

| Script                                      | Purpose                                                      |
|---------------------------------------------|--------------------------------------------------------------|
| [`collector.lua`](../../scripts/mm2-candy-farm/collector.lua) | Farms candies: noclip + hover + fly to nearest safe coin, every frame |
| [`box_opener.lua`](../../scripts/mm2-candy-farm/box_opener.lua) | Spends 600 candies in the Halloween2026Box as soon as you have them  |

Author of v0.1: Tormenta_2336. Adopted into Curry Launcher on 2026-11-10.

## Collector architecture

Single `RunService.Heartbeat` loop, ~60fps. Gated by `shouldFarm()`:

1. **Spectator gate** — no `"waiting for your turn"` TextLabel in `PlayerGui`
2. **Coins gate** — `workspace.<Map>.CoinContainer` has at least one child
3. **Role gate** — player holds a `Tool` (role has been assigned)

When all three pass:
- `Humanoid.PlatformStand = true` (disable Humanoid physics)
- `CanCollide = false` on every `BasePart` of the character (re-applied per frame)
- `BodyVelocity` (`FarmBV`) on the HRP with `MaxForce = (0, 1e6, 0)` to cancel gravity
- `getDanger()` collects every hostile tool carrier (knife always, gun only when we are innocent)
- Immediate flee when inside 60% of a threat's safe radius
- Otherwise `getBestCoin()` picks the nearest safe coin, fallback nearest overall
- Target position = coin.Y − 1.5 so the head (sitting 1.5 above the HRP) collides with the coin

Visited coins live in a `{coin → tick()}` table that expires at 0.8 s.

## Box opener architecture

Simple `task.spawn` loop:

1. Poll `ProfileData.Materials.Owned.Candies2026` every `CHECK_DELAY` seconds
2. If `>= 600`, invoke `ReplicatedStorage.Remotes.Shop.OpenCrate` with
   `("Halloween2026Box", "MysteryBox", "Candies2026")`
3. Confirm by comparing balance before/after (the server returns `false`
   when the Shop UI isn't active even though the purchase went through)
4. Stop after `MAX_FAIL = 3` consecutive failures

## Known pain points (targets for optimization)

- `workspace:GetChildren()` scanned every frame to locate `CoinContainer`
- `getDanger()` walks all players every frame
- `applyNoclip()` walks the entire character tree every frame — slow on avatars with many accessories
- `HEAD_OFFSET = 1.5` hard-coded, breaks on bundles that move the head
- Threat check is radius-only; no line-of-sight
- `visited` expiry (0.8 s) can be wrong on laggy servers

## MCP Roblox executor

The operator installed an MCP Roblox executor tool so I can connect to
the live game and iterate on these scripts against real round data.
As of the baseline check it wasn't yet visible in my tool list — may
need a Claude Code session restart to register.

Once visible, planned work:
- Capture one full round of coin positions and danger events, use them
  as a replay to profile per-frame cost of the gates and the inner loop
- Replace the per-frame `workspace:GetChildren()` scan with a cached
  `CoinContainer` reference invalidated on round-end
- Replace `applyNoclip` with a `DescendantAdded` connection
- Add a dynamic head-offset probe

See also: [[versions]], [[changelog]], [[scripting]], [[lua-luau]],
[[rakbot-analysis/overview]].

# MM2 Candy Farm — v0.1

Two LocalScripts for Murder Mystery 2 (Roblox) Halloween 2026 candy farm
and auto-opening the 600-candy Halloween box.

Author: Tormenta_2336 · Baseline tagged as v0.1 in Curry Launcher.

## Files

### `collector.lua`
Candy collector. Single `RunService.Heartbeat` loop. Three gates decide
whether to farm; when all pass, enables noclip + hover, picks the nearest
safe coin, and flies to it.

Tunables (top of file):

| Constant        | Default | Meaning                                                      |
|-----------------|---------|--------------------------------------------------------------|
| `SPEED`         | `26`    | Movement speed toward the coin (studs/second)                |
| `COIN_REACH`    | `1.2`   | Snap radius — within this distance the coin is picked up     |
| `HEAD_OFFSET`   | `1.5`   | Y offset so the head touches the coin (the head sits 1.5 above HRP) |
| `MURDER_SAFE`   | `35`    | Flee radius around a knife carrier                           |
| `SHERIFF_SAFE`  | `20`    | Flee radius around a gun carrier (only when we are innocent) |

Kill switch: set `running = false` to stop the Heartbeat.

### `box_opener.lua`
Auto-opener for `Halloween2026Box`. Loops every `CHECK_DELAY` seconds; as
soon as `Candies2026 >= 600` it calls
`ReplicatedStorage.Remotes.Shop.OpenCrate:InvokeServer("Halloween2026Box", "MysteryBox", "Candies2026")`
and confirms the opening by comparing the candy balance before and after.

Tunables:

| Constant        | Default              | Meaning                               |
|-----------------|----------------------|---------------------------------------|
| `BOX_ID`        | `Halloween2026Box`   | Internal shop item id                 |
| `CURRENCY`      | `Candies2026`        | Event currency name                   |
| `BOX_COST`      | `600`                | Price per box                         |
| `CHECK_DELAY`   | `3`                  | Seconds between checks (anti-spam)    |
| `MAX_FAIL`      | `3`                  | Consecutive failures before giving up |

Kill switch: set `autoRunning = false`.

## Suggested usage

1. Run `collector.lua` first — it starts the candy farm.
2. Run `box_opener.lua` in parallel — it opens a box every time the balance
   reaches 600.

Both scripts are self-contained LocalScripts. They must be injected
through an executor with full `game.ReplicatedStorage` access and the
ability to invoke RemoteFunctions as the local player.

## Known trade-offs / things to improve

- `collector.lua` reads `workspace:GetChildren()` every frame for coin
  containers — fine for small maps, could be cached when the round starts
- `getDanger()` walks every player on every frame — could update less
  frequently and cache the result for N ms
- `applyNoclip` walks every descendant each frame; when the character has
  many accessories this adds up — switch to a touched-connection or a
  per-added-part hook
- The current Y-offset hack (`HEAD_OFFSET = 1.5`) assumes an R15/R6
  character with a stock head height; some bundles move the head and the
  pickup breaks — detect the head's local Y offset dynamically
- Danger evasion only considers tool carriers; no line-of-sight check,
  so we can be shot through walls while thinking we are safe
- `visited` expiry is 0.8s — too short for lagged servers, too long for
  rapid-fire pickups; should key on the coin's `Parent` nil-check too

The MCP Roblox executor (once visible to the AI) will let us probe the
live game and verify these pain points against real round data.

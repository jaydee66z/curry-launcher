# Reference — Main.luau API

> Cómo usar / configurar / hackear el script Luau si rollbackeás a él.

## Setup

```lua
-- Opcional: pre-cargar webhook URL
_G.farmWebhookUrl = "https://discord.com/api/webhooks/..."

-- Load Main.luau (executor-dependent, ej Synapse):
loadstring(readfile("Main.luau"))()
```

El script autoarranca. No necesita más.

## Features

Todas activables/desactivables via CONFIG table al top del script:

### FARM_COINS

```lua
FARM_COINS = true   -- default
```

Si false → NO farma. Bot idle en lobby/map.

### STOP_AT_CANDIES

```lua
STOP_AT_CANDIES = 50  -- default
```

Al llegar a N candies por round, bot stops y stays idle hasta próxima round.

Útil para simular "jugador que dejó de jugar" a ciertos puntos → menos sospechoso que farmear 100+ candies.

### AUTO_BUY_BOX

```lua
AUTO_BUY_BOX = true
BOX_BUY_THRESHOLD = 600
BOX_NAME = "Halloween2026Box"
```

Parallel task que cada 3s revisa Candies2026 ≥ 600 y abre box.

### AUTO_REJOIN

```lua
AUTO_REJOIN = true
REJOIN_POLL_INTERVAL = 1.0
```

Watchdog que detecta `GuiService:GetErrorCode()` != OK o CoreGui prompt con "Invalid position" → teleport a nueva instancia.

### FREEZE_ANIMATIONS

```lua
FREEZE_ANIMATIONS = true
```

Para toda animation playing cada 0.1s en parallel task. Modelo queda "estático" visualmente mientras HRP se mueve via CFrame.

### HUMANIZED

```lua
HUMANIZED = false  -- default en v0.42+
```

Si true → humanoid camina real (anims playing). Si false → PlatformStand + CFrame-step (modelo congelado, movimiento instant).

Operator prefiere `false` ("modelo estático").

### MAX_PICK_DISTANCE

```lua
MAX_PICK_DISTANCE = 240  -- studs
```

Distancia máxima que persigue un candy. Más alto = más coverage but más risk de cruzar void.

### SPEED

```lua
SPEED = 26  -- studs/sec
```

Velocidad del CFrame step. 26 = reference bot normal. 16 = default walkspeed (más safe AC).

### Hover / BV

```lua
-- Siempre on, no configurable. BV:
-- MaxForce = Vector3.new(0, 1e6, 0)  -- Y-only
-- Velocity = Vector3.zero
```

Mantiene Y estable → no cae.

### Noclip

```lua
-- Siempre on via RNS.Stepped. Setea CanCollide=false en:
-- HRP, LowerTorso, UpperTorso, Head, resto de char parts
```

### Map visual hide

```lua
hideMapVisual = true  -- via hideModelVisual() call
```

En CoinsStarted, oculta map parts (Transparency=1, CastShadow=false). Preserva colisión → no cae.

### Lobby visual hide

```lua
hideLobbyVisual = true  -- parallel task cada 8s
```

Idem pero para workspace children no-map (lobby structures).

## Telemetría (_G.farmDebug)

```lua
_G.farmDebug = {
    myRole,               -- "innocent"/"sheriff"/"murderer"
    wasFarming,           -- bool
    candiesThisRound,     -- int
    lifetimeCandies,      -- int (session)
    profileCandies,       -- int (from ProfileData, lo que tenés en inventory)
    tripCoinID,           -- "Candy" o "none" o "stopped-at-threshold"
    parkedCoinID,         -- coin que estás parkeando
    boxesOpened,          -- cuántas boxes abriste
    lastBoxItem,          -- qué item cayó en última box
    lastKickReason,       -- si hubo kick + motivo
    rejoinCount,          -- cuántas veces auto-rejoined
    heartbeatTick,        -- timestamp del último tick (self-heal)
    hbRebuildCount,       -- cuántas veces el watchdog resucitó el heart
    lastError,            -- último error capturado por pcall
    headOffset,           -- 1.5 para R6, 1.86 para R15
    mapHiddenParts,       -- cuántos parts ocultados por hideMapVisual
    mapNoclipParts,       -- cuántos noclipped en map (típicamente 0 en v0.44+)
    boxCurrency,          -- "Candies2026"
}
```

Ver estado:
```lua
print(game:GetService("HttpService"):JSONEncode(_G.farmDebug))
```

## Kill switch

```lua
running = false
```

Mata el Heartbeat + todas las parallel tasks (watchdog, box opener, anim freezer, inventory watcher, lobby hider).

Restart:
```lua
-- loadstring del Main.luau de vuelta
```

## Debug levels

```lua
CONFIG.DEBUG_LOG = true     -- print "[farm]" lines (rate-limited 250ms)
CONFIG.DEBUG_EXPOSE = true  -- populate _G.farmDebug
```

Para prod: DEBUG_LOG=false para reducir console spam. DEBUG_EXPOSE=true siempre para monitoring.

## Inventory watcher

Parallel task que snapshots `ProfileData.Weapons.Owned` al load, y cada 2s diffea. Si aparece "Embersickle" o "EmbersickleChroma" → webhook a `_G.farmWebhookUrl`.

## Kick auto-rejoin

Si Roblox dispara disconnect:
1. Watchdog detecta vía GuiService + CoreGui scan
2. Fire TeleportService:Teleport(placeId, lp) a new instance
3. Webhook de Discord: "KICK → rejoining"
4. `_G.farmRejoinCount`++

## Comportamiento por ronda

```
Round starts (CoinsStarted fire):
  → map noclip applied (3000+ parts)
  → visited + attempts tables cleared
  → candiesThisRound = 0
  → tripCoinID set as "Candy" cuando pickea uno
  
Loop (20Hz heartbeat):
  if candiesThisRound >= 50:
    tripCoinID = "stopped-at-threshold"
    hover + anim freeze, no movement
    skip heavy work
  else:
    pick best coin (nearest + score)
    move hacia él (CFrame step o MoveTo)
    park cuando within reach radius
    wait for Collected flag
  
Round ends:
  stopFarm() called
  wasFarming = false
  (next CoinsStarted resetea todo)
```

## Links

- [[00-mm2-game-flow]]
- [[../mm2-port/01-architecture]]
- [[../advanced/03-luau-executor-fallback]]

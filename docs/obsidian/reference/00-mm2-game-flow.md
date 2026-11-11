# Reference — MM2 game flow

> Entender el loop del juego para poder modelar el bot correctamente.

## Round lifecycle

```
[Lobby] ──► [Countdown 10s] ──► [Round active 2-5 min] ──► [Round end] ──► [Lobby]
               │                        │                        │
               ▼                        ▼                        ▼
         CoinsStarted            CoinCollected events    (CoinsStarted next)
         fires                   firing (as players             round resets
                                 pick candies)                  candiesThisRound
```

### Lobby

- Players chilling en el lobby (área estática pre-round)
- NO coins visible
- Countdown visual al próximo round (10s)
- Bot: `wasFarming=false`, pinned en pos (no cae)

### Countdown

- Last 10s pre-round
- Server elige murderer + sheriff random
- Mapa se carga (los 9 mapas rotan)
- Bot: pre-pare para engage, pero shouldFarm aún false

### Round active

- Players teleportados al map
- Coins spawnean en posiciones fijas del map (~50-80 coins por round)
- Murderer y sheriff hidden (knife/gun en backpack)
- Coins se recogen vía `.Touched` en Coin_Server part
- Server fire `CoinCollected` broadcast per pickup
- Round termina cuando:
  - Murderer mata a todos los innocents
  - Sheriff mata al murderer
  - Timer expiró (~5 min)

### Round end

- Short "results" screen
- Teleport de vuelta a lobby
- `candiesThisRound` para el bot debe resetear

## Roles

### Innocent (~10 players)

- No weapon
- Objetivo: survive + farm candies
- Our bot farmea en este rol (lo más común)

### Sheriff (1 player)

- Starts con Gun equipped
- Objetivo: matar al murderer
- Our bot: podría shoot al detectar murderer (NO implementado, COMBAT_ENABLED=false)

### Murderer (1 player)

- Starts con Knife equipped
- Objetivo: matar a todos los innocents
- Our bot: NO ataca (safe mode)

## Economía de candies

### Candies2026 (currency)

- Cada coin recogido = 1 candy
- Al terminar round, candies van a ProfileData.Materials.Owned.Candies2026
- Máximo por round observado: ~50-70 candies (si farm all map)
- Nuestro STOP_AT_CANDIES=50 asume 50 es "max human-like"

### Halloween2026Box

- Costo: 600 candies
- Contiene: 10 Legendary (common pool) + 1 Godly (Embersickle)
- OpenCrate:InvokeServer("Halloween2026Box", "MysteryBox", "Candies2026") devuelve el item key
- Drop rate Godly: estimado 1/500

### Items dropeables

Common (Legendary tier):
- Skulls_K_2026, Bullets_K_2026 (knives)
- Catseye_K_2026, Raven_K_2026, Drool_K_2026, Brew_K_2026 (knives)
- CandyCorn_G_2026, Bombs_G_2026, Glow_G_2026, Embergun_G_2026 (guns)

Godly: **Embersickle** (knife) y variant **EmbersickleChroma**.

## Maps (9 en rotación standard)

1. Farmhouse (zombies rounds)
2. Manor
3. Mansion2
4. VampireCastle
5. Spaceship
6. MilBase
7. Mineshaft
8. Bank2
9. ResearchFacility

Capturados en `mm2-maps/<name>.json` via `map_recon.lua`.

## Server mechanics

- 12 players max per server
- Rounds consecutivos sin reload
- Después de N rondas (10-15) el server reinicia (nuevo map rotation starts)
- JobId constante por server lifetime

## Event remotes

| Remote | Direction | Purpose |
|--------|-----------|---------|
| `CoinsStarted` | S → C | Nueva round, candies spawned |
| `CoinCollected` | S → C | Un candy fue collected (tuyo o de otro) |
| `GetCoin` | C → S | Request pickup del coin X |
| `OpenCrate` | C → S (invoke) | Open box |

## Timing

- Round start → CoinsStarted → +2s delay → coins fully populated
- Tick rate server: ~30 Hz
- Nuestro Session.tick: 20 Hz (50ms interval)

## Bot behavior ideal

```
wait for CoinsStarted
  reset candies_this_round = 0
  clear visited coins
loop until round end:
  if candies_this_round >= 50:  // STOP_AT_50
    idle (don't fire)
  else:
    pick nearest uncollected coin
    (optional phase 2: move to it)
    fire GetCoin:FireServer(coin)
    wait for CoinCollected confirmation
    candies_this_round++

at round end:
  wait for next CoinsStarted

periodically:
  if Candies2026 >= 600:
    fire OpenCrate
    verify candies decreased
    boxes_opened++
```

## Edge cases observados

### Coin "fantasma"

A veces el server marca un coin Collected pero el cliente no lo ve (replication delay). Bot puede intentar fire → ignored.

Mitigación: `MAX_FIRES_PER_COIN=2` + `CONFIRM_TIMEOUT` → skip coins stuck.

### Candy en void (fuera de map)

Algunos candies spawnean en posiciones imposibles de acceso. Bot puede chase → cae al void.

Mitigación: `MAX_PICK_DISTANCE=240` + walkable grid (phase 2).

### Round-end trampa

Si bot sigue persiguiendo coins durante round-end transition → puede terminar en void entre rounds.

Mitigación: watch `waitingLabel.Visible` → cuando true, stopFarm.

### Murderer knife visible

Si vas sheriff y detectás murderer, PODRÍAS shoot. NO implementado (COMBAT_ENABLED=false).

## Links

- [[../mm2-maps/00-catalog]]
- [[../api-reference/02-mm2-remotes]]
- [[../mm2-port/00-status]]

# Reference — all config knobs

> Matriz completa de todos los CONFIG values en el projecto, con defaults + rangos.

## Main.luau — CONFIG table

### Features

| Clave | Default | Rango | Propósito |
|-------|---------|-------|-----------|
| `FARM_COINS` | true | bool | Activar farm loop |
| `DEBUG_LOG` | true | bool | Print `[farm]` lines |
| `DEBUG_EXPOSE` | true | bool | Mirror state a _G.farmDebug |

### Combat (disabled)

| Clave | Default | Propósito |
|-------|---------|-----------|
| `COMBAT_ENABLED` | false | Master switch |
| `COMBAT_AT_CANDIES` | 999 | Threshold para activar combat |
| `SHERIFF_SHOOT_RANGE` | 60 | Studs |
| `TIME_BETWEEN_SHOTS` | 3.4 | Gun reload |
| `STAB_RANGE` | 12 | Knife range |
| `TIME_BETWEEN_STABS` | 1.5 | Stab cooldown |

### Movement

| Clave | Default | Propósito |
|-------|---------|-----------|
| `HUMANIZED` | false | MoveTo vs CFrame-step |
| `FREEZE_ANIMATIONS` | true | Stop anim tracks cada 0.1s |
| `SPEED` | 26 | Studs/sec (CFrame cadence) |
| `FORCE_WALKSPEED` | 16 | Humanoid.WalkSpeed value |
| `MAX_FRAME_STEP` | 1.1 | Studs max per frame |
| `MAX_DT` | 0.05 | Clamp dt para evitar lag spike |
| `MAX_JUMP` | 25 | Studs max CFrame jump (AC safety) |
| `TIME_ON_COIN` | 1.0 | Park duration |
| `RETRY_AFTER` | 0.4 | Seconds before re-selecting same coin |
| `MAX_ATTEMPTS` | 4 | Fire attempts before marking visited |
| `STUCK_TIMEOUT` | 6.0 | Seconds hasta considerar stuck |
| `START_DELAY` | 2 | Seconds post-round-start antes de farm |
| `MAP_MARGIN` | 20 | Studs margin del bbox |
| `COOLDOWN_BETWEEN_COINS` | 0.1 | Pause entre pickups |
| `MICRO_PAUSE_MIN` | 0 | Random pause lower (humanized) |
| `MICRO_PAUSE_MAX` | 0 | Random pause upper |
| `SNAP_FINAL_DISTANCE` | 0 | Snap distance en reach |
| `JUMP_CHANCE` | 0 | 0..1, prob de jump per frame |
| `JUMP_COOLDOWN` | 999 | Seconds between jumps |

### Pickup

| Clave | Default | Propósito |
|-------|---------|-----------|
| `COIN_PICK_RADIUS` | 1.5 | Studs HRP→coin para park |
| `SNAP_ON_REACH` | true | CFrame snap on reach |
| `AIM_AT_TORSO` | true | Target coin.Position (torso center) |
| `USE_GETCOIN_REMOTE` | true | Fire GetCoin:FireServer fallback |
| `PICK_FIRE_RADIUS` | 6 | Fire GetCoin si dentro |
| `FIRE_CONFIRM_TIMEOUT` | 0.35 | Espera por server ack |
| `FIRES_PER_COIN` | 2 | Retry budget |

### Pathing intelligence

| Clave | Default | Propósito |
|-------|---------|-----------|
| `WALL_RAYCAST` | true | Count walls para score |
| `WALL_PENALTY` | 12 | Studs equiv per wall |
| `MAX_WALLS_HARD_LIMIT` | 99 | Rechazar si > N (default: no reject) |
| `FAR_WITH_WALLS_LIMIT` | 9999 | Defer coin si far + walled |
| `NEAR_PREFERENCE_RADIUS` | 25 | Bonus para near coins |
| `MAX_PICK_DISTANCE` | 240 | Hard cap chase distance |
| `RESCUE_IF_NO_COIN_WITHIN` | 300 | Rescue if nearest > N |
| `USE_WALKABLE_GRID` | false | Pathfinder phase 2 filter |
| `WALKABLE_SEARCH_RADIUS` | 25 | Studs from coin a nearest walkable |
| `WALKABLE_HARD_FILTER` | false | Reject coin sin walkable nearby |

### Rescue

| Clave | Default | Propósito |
|-------|---------|-----------|
| `BELOW_MAP_Y_DELTA` | -80 | Trigger if HRP.Y < bbox_bottom + this |

### Smoothing

| Clave | Default | Propósito |
|-------|---------|-----------|
| `DIR_SMOOTH` | 0.25 | Lerp factor para heading |
| `SYNC_VELOCITY` | true | Write AssemblyLinearVelocity |
| `FACE_MOVE_DIR` | true | CFrame.lookAt orientation |

### Box opener

| Clave | Default | Propósito |
|-------|---------|-----------|
| `AUTO_BUY_BOX` | true | Enable |
| `BOX_BUY_THRESHOLD` | 600 | Candies required |
| `BOX_NAME` | "Halloween2026Box" | Box key |

### Webhook

| Clave | Default | Propósito |
|-------|---------|-----------|
| `WEBHOOK_URL` | (from _G.farmWebhookUrl) | Discord endpoint |
| `NOTIFY_ITEMS` | {Embersickle, EmbersickleChroma} | Which items trigger notify |

### Auto-rejoin

| Clave | Default | Propósito |
|-------|---------|-----------|
| `AUTO_REJOIN` | true | Enable |
| `REJOIN_POLL_INTERVAL` | 1.0 | Seconds |
| `STOP_AT_CANDIES` | 50 | Round threshold |
| `COMBAT_AT_CANDIES` | 999 | Combat threshold |

### Stop

| Clave | Default | Propósito |
|-------|---------|-----------|
| `STOP_AT_CANDIES` | 50 | Idle al llegar a N |

## Python mm2_client.py

### Constants

| Clave | Default | Propósito |
|-------|---------|-----------|
| `TICK` | 0.05 | Loop interval (seconds) |
| `MAX_PICK_DISTANCE` | 240 | Studs chase cap |
| `MAX_FIRES_PER_COIN` | 2 | Fire budget |
| `CONFIRM_TIMEOUT` | 0.6 | Wait between re-fires |
| `VISIT_AFTER_FAILS` | True | Bury after exceeding budget |
| `BOX_THRESHOLD` | 600 | Candies req para open |
| `BOX_POLL_INTERVAL` | 3.0 | Seconds |

## Python mm2_wire.py

Constants (no config, hardcoded):
- `DATA_OPCODE` = `b'\x83'`
- `EVENT_ITEM_OPCODE` = `b'\x07'`
- `REMOTE_GETCOIN_PATH` = (b"ReplicatedStorage", b"Remotes", b"Gameplay", b"GetCoin")
- `REMOTE_OPENCRATE_PATH` = (b"ReplicatedStorage", b"Remotes", b"Shop", b"OpenCrate")

## Python mm2_inventory.py

| Clave | Default | Propósito |
|-------|---------|-----------|
| `NOTIFY_ITEMS` | {"Embersickle":"common","EmbersickleChroma":"chroma"} | Items a watch |
| `EmbersickleWatcher.POLL` | 2.0 | Seconds between Weapons.Owned checks |

## Python proxy_pool.py

Constants:
- `_DEFAULT_PATHS` = ("proxies.txt", "proxies.local.txt", "proxies.list")

## Python bootstrap.py

| Clave | Default | Propósito |
|-------|---------|-----------|
| `RobloxHTTP.__init__ timeout` | 10 | Seconds per request |
| `MAX_RESPONSE` | ~16 KB | Response size cap |

## Python mass.py

| Clave | Default | Propósito |
|-------|---------|-----------|
| `MAX_ACCOUNTS` | 999999 | Upper limit |

## Environment variables

| Var | Propósito |
|-----|-----------|
| `MM2_DISCORD_WEBHOOK_URL` | Discord webhook para drops/alerts |

## Links

- [[01-main-luau-reference]]
- [[../mm2-port/00-status]]

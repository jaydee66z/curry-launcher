# MM2 Port — Session tick loop

## Estado de una Session

```python
@dataclass
class Session:
    inspector: object        # rakbot.replication.Inspector
    transport: object        # rakbot.persistent_client.PersistentTransport
    emit: callable           # json-line emitter to mass_worker stdout
    
    attempts: dict           # {coin_key: CoinAttempt(last_fire, fires)}
    visited: set             # {coin_key, ...} buried for this round
    candies_this_round: int
    lifetime_candies: int
    boxes_opened: int
    next_box_poll: float
    next_invocation_id: int
    _last_tick: float
```

## Cadencia: `TICK = 0.05` (20 Hz)

```
┌─────────────────────────────────────────────────────┐
│  Session.run(duration, dry_run):                    │
│    while deadline > now:                            │
│       try: self.tick()                              │
│       except CryptoError → emit tick_err           │
│       except Exception    → emit tick_exception    │
│       time.sleep(TICK)                              │
└─────────────────────────────────────────────────────┘
```

## `tick()` — una decisión

```
def tick(self):
    hrp = _hrp_position(self.inspector)
    if hrp is None: return             # char not spawned yet
    picked = self._pick_target(hrp)    # nearest Coin_Server within 240 studs
    if picked is not None:
        self._fire_coin(picked[0])     # transport.send(GetCoin payload)
    self._maybe_open_box()             # every 3s check Candies2026 ≥ 600
```

## `_pick_target(hrp)` — selección

```
Scan inspector.nodes:
   for each (key, node) in nodes.items():
      skip if key in visited
      skip if not is Coin_Server Part
      skip if is Collected
      pos = node.props.CFrame.position
      skip if pos missing
      d = distance_3d(pos, hrp)
      skip if d > MAX_PICK_DISTANCE (240)
      
      attempt = attempts.get(key)
      if attempt.fires >= MAX_FIRES_PER_COIN (2):
         visited.add(key)
         skip
      if attempt and os.monotonic() - attempt.last_fire < CONFIRM_TIMEOUT (0.6):
         skip  # wait for server to confirm previous fire
      
      if d < best: best, best_dist = key, d

return best or None
```

Resultado: la coin pickeada es la **más cercana** que (a) no se intentó hace <0.6s, (b) no se agotó el budget de 2 fires, (c) está dentro de 240 studs, (d) tiene CFrame disponible en el world.

## `_fire_coin(coin_key)` — envío

```
payload = mm2_wire.getcoin_payload(inspector, coin_key)
if payload is None:
   return False  # remote not discovered yet
try:
   transport.send(payload)
except Exception as e:
   emit transport_err event
   return False
attempts[coin_key].fires += 1
attempts[coin_key].last_fire = now
return True
```

## `_maybe_open_box()` — box opener

```
now = os.monotonic()
if now < next_box_poll: return
next_box_poll = now + 3.0 (BOX_POLL_INTERVAL)

candies = mm2_inventory.read_candies(inspector)
if candies is None or candies < 600 (BOX_THRESHOLD):
   return

payload = mm2_wire.opencrate_payload(inspector, next_invocation_id)
if payload is None: return  # remote not discovered

next_invocation_id += 1
transport.send(payload)
boxes_opened += 1
emit box_fired event
```

## Hooks externos

### `on_coins_started()`
Llamado cuando el server fire `CoinsStarted` (ninguna arg).
Resetea `attempts`, `visited`, `candies_this_round = 0`.

### `on_coin_collected(coin_type: bytes)`
Llamado cuando el server fire `CoinCollected` con el type de coin.
Incrementa `candies_this_round` y `lifetime_candies`.

Ambos se wirean desde `mass_worker.run_mm2_farm()` interceptando `inspector.event_value`.

## Dry run

```
session.run(dry_run=True)
```

Monkey-patcheá `transport.send` con una función que loguea JSON:
```json
{"event": "mm2", "dry_send": {"bytes": 23, "head": "8307010101..."}}
```

y restaurá el original al salir del `run`. Zero AC risk porque no envía ningún UDP.

## Métricas que emite el Session

Todos vienen como JSON lines del subprocess:

| Evento | Campos | Cuando |
|--------|--------|--------|
| `round_start` | — | on_coins_started() |
| `pickup` | type, round, life | on_coin_collected() |
| `box_fired` | boxes_opened, candies_before | invoke OpenCrate |
| `transport_err` | stage (getcoin/opencrate), err | transport.send exception |
| `tick_err` | err (CryptoError str) | wire encoder returned bad data |
| `tick_exception` | err (repr) | unexpected Python exception |
| `dry_send` | bytes, head | solo en dry_run mode |

## Diseño anti-stall

| Problema | Mitigación |
|----------|-----------|
| Coin que no pickea (server ignora) | `MAX_FIRES_PER_COIN=2` → visited |
| Coin fuera del mapa | `MAX_PICK_DISTANCE=240` |
| Spam al mismo coin dentro de 600ms | `CONFIRM_TIMEOUT=0.6` |
| Remote no está en el world yet | `getcoin_payload` devuelve None → no-op |
| Character no spawneado | `_hrp_position` devuelve None → tick silent |

## Links

- [[00-status]]
- [[01-architecture]]
- [[02-wire-protocol]]
- [[04-navigation-roadmap]] — qué agregar si GetCoin requiere proximidad real

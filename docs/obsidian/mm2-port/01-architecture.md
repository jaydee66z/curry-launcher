# MM2 Port — arquitectura

## Capas

```
┌─────────────────────────────────────────────────────────┐
│  rakbot.mass  (orchestrator — process-per-account)      │
│  ────────────────────────────────────────────           │
│   MassRunner(mm2=True, mm2_dry_run=False).launch(N)     │
│   → spawns N subprocesses of mass_worker.py             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ one subprocess per cookie
┌─────────────────────────────────────────────────────────┐
│  rakbot.mass_worker  (per-account entry)                │
│  ────────────────────────────────────────────           │
│   1. Read cookie from stdin                             │
│   2. ProxyPool.url_for(cookie_hash) → pin IP            │
│   3. RobloxBootstrap(credential, proxy_pool=pool)       │
│   4. authenticate() → user_id                           │
│   5. prepare(place_id=142823291) → connection info      │
│   6. GameClient(info) in thread                         │
│   7. Session(inspector, transport).run(dry_run=…)       │
│   8. EmbersickleWatcher(inspector).start()              │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ shared Inspector, shared transport
┌─────────────────────────────────────────────────────────┐
│  rakbot.mm2_client  (per-session farm logic)            │
│  ────────────────────────────────────────────           │
│   Session.tick():                                       │
│     • Resolve HRP position from inspector.nodes         │
│     • Pick nearest Coin_Server within 240 studs         │
│     • Fire GetCoin:FireServer(coin) via mm2_wire        │
│     • Bump attempts[coin], mark visited after 2 fails   │
│     • Every 3s: read ProfileData.Candies2026            │
│       → if ≥600, invoke OpenCrate                       │
└─────────────────────────────────────────────────────────┘
       │                                           │
       ▼                                           ▼
┌─────────────────┐                     ┌─────────────────┐
│ rakbot.mm2_wire │                     │ mm2_inventory   │
│  ──────────────│                     │  ──────────────│
│  Payload bytes  │                     │  ProfileData    │
│  (heli_wars     │                     │  snapshot +     │
│   pattern)      │                     │  Discord webhook│
└─────────────────┘                     └─────────────────┘
       │                                           │
       ▼                                           ▼
┌─────────────────────────────────────────────────────────┐
│  rakbot.persistent_client + rakbot.native_crypto        │
│  ────────────────────────────────────────────           │
│   UDP transport (RakNet + ChaCha20)                     │
└─────────────────────────────────────────────────────────┘
```

## Responsabilidades por módulo

| Módulo | Entrada | Salida | Side effects |
|--------|---------|--------|-------------|
| `mass.py::MassRunner` | lista de `Credential` | subprocesses | spawns `mass_worker.py` |
| `mass_worker.py::run_mm2_farm` | argv + stdin cookie | `emit()` JSON lines | joins game, runs tick loop |
| `mm2_client.py::Session.tick` | Inspector snapshot | ninguna | fires UDP payloads via transport.send |
| `mm2_client.py::Session.run` | duration, dry_run | — | loop @ 20Hz, calls tick() |
| `mm2_wire.py::getcoin_payload` | inspector, coin_key | bytes payload or None | ninguno |
| `mm2_wire.py::opencrate_payload` | inspector, invocation_id | bytes payload or None | ninguno |
| `mm2_inventory.py::read_candies` | inspector | int or None | ninguno |
| `mm2_inventory.py::EmbersickleWatcher` | inspector, username, user_id | — | daemon thread, HTTP POST a Discord |

## Flujo de datos

### Pickup (una ronda completa)

```
MM2 server teleporta player ──► JoinData llega ──► Inspector llena nodes
                                                    │
                       CoinsStarted RemoteEvent ◄───┤ (observed via inspector.event_value)
                       │
          Session.on_coins_started() ──► clear visited, attempts, candiesThisRound=0
                                                    │
                      Coin_Server parts aparecen en inspector.nodes
                                                    │
                       Session.tick() @ 20Hz ◄──────┤
                         │
                         ├── _pick_target(hrp) → nearest coin
                         ├── mm2_wire.getcoin_payload(coin) → bytes
                         └── transport.send(payload)
                                                    │
                       CoinCollected fires de vuelta ◄─ server ack
                         │
                       Session.on_coin_collected(b'Candy')
                         candies_this_round += 1
                         lifetime_candies += 1

                       Si candies_this_round >= 50 (STOP_AT_50) → no más fires, idle
                       Si ProfileData.Candies2026 >= 600:
                         mm2_wire.opencrate_payload(invocation_id)
                         transport.send(…)
                         EmbersickleWatcher ve nuevo item en Weapons.Owned
                         → webhook POST a Discord
```

## Comparación con Main.luau

| Función | Main.luau (executor) | mm2_py (Rakbot nativo) |
|---------|----------------------|------------------------|
| Movimiento | `Humanoid:MoveTo` + hover BV | ❌ no implementado (fase 2) |
| Noclip | `CanCollide=false` per frame | ❌ no aplica (sin character físico local) |
| Pickup | Touched + `GetCoin:FireServer(coin)` | ✅ `GetCoin` via UDP payload |
| Box opener | parallel task: `OpenCrate:InvokeServer` | ✅ `OpenCrate` via UDP payload |
| Webhook drops | per-frame `_G.farmDebug` watcher | ✅ `EmbersickleWatcher` daemon thread |
| Auto-rejoin | CoreGui + GuiService watchers | parcial (vía RobloxBootstrap errors) |
| Self-heal heartbeat | v0.49 watchdog + rebuild | N/A (Python tiene uncaught exc → crash → mass.py relaunch) |
| Anim freeze | `Animator:Stop()` cada frame | N/A (no character local) |
| Mapa noclip visual | `Transparency=1` + CastShadow=false | N/A |
| STOP_AT_CANDIES=50 | sí | ✅ sí (se chequea candidate pick) |
| MAX_PICK_DISTANCE=240 | sí | ✅ sí |

## Links

- [[00-status]] — status report
- [[02-wire-protocol]] — bytes exactos
- [[03-session-loop]] — tick-level flow
- [[04-navigation-roadmap]] — fase 2
- [[../rakbot-analysis/architecture]] — arquitectura Rakbot original

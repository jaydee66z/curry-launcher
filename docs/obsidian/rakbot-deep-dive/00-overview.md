# Rakbot deep dive — overview

Documentación granular de cada módulo Python del cliente nativo Rakbot. Útil para debugging y para onboarding de nuevos devs.

## Módulos core

| Módulo | Responsabilidad | LOC approx |
|--------|----------------|-----------|
| `bootstrap.py` | HTTPS auth + join preparation | 400 |
| `native_crypto.py` | X25519 + ChaCha20-Poly1305 AEAD | ~200 |
| `native_open.py` | Two-step offline open handshake | ~150 |
| `native_client.py` | Persistent native transport | ~300 |
| `persistent_client.py` | Keepalive, retry, split TTL | ~400 |
| `protocol.py` | RakNet offline negotiation | ~250 |
| `reliability.py` | Datagram/frame codec | ~500 |
| `application.py` | Application envelope | ~400 |
| `application_crypto.py` | Legacy AES envelope cipher | ~150 |
| `schema.py` + `isr.py` | Native 0.744 schema + ISR | ~800 |
| `replication.py` | Bounded Data reader (NEVER executes Luau) | 740 |
| `node_store.py` | OrderedDict of nodes with eviction policy | ~100 |
| `physics.py` | Native 0.744 physics quantization | ~300 |
| `game_client.py` | High-level API combining the above | ~500 |
| `joiner.py` | Pinned-server persistent character | 154 |
| `chat.py` + `commands.py` | Chat interface | ~300 |

## Módulos per-game

| Módulo | Game |
|--------|------|
| `egg_client.py`, `egg_catalog.py`, `egg_schedule.py`, `egg_filter.py`, `egg_history.py`, `egg_sessions.py` | Steal An Egg scanner |
| `brainrot.py`, `brainrot_data.py`, `brainrot_wire.py` | Steal a Brainrot scanner |
| `heli_wars.py` | Heli Wars team selector |
| `mm2_wire.py`, `mm2_client.py`, `mm2_inventory.py` | **MM2 farm (nuestro port)** |

## Módulos de orchestration

| Módulo | Función |
|--------|---------|
| `__main__.py` | CLI entry |
| `mass.py` | Mass-account runner |
| `mass_worker.py` | Per-account subprocess |
| `scan_pool.py`, `scan_processes.py` | Scanner pool |
| `server_pool.py` | Public server browser |
| `scanner_health.py` | Health checker |

## Módulos GUI

| Módulo | Función |
|--------|---------|
| `gui.py` | Tkinter root |
| `gui_onyx.py` | Dark theme |
| `gui_support.py` | Utilities |
| `gui_worker.py` | GUI thread handoff |

## Módulos networking

| Módulo | Función |
|--------|---------|
| `relay.py` | WebSocket broadcast |
| `data_ping.py` | Latency check |

## Módulos Luau static

| Módulo | Función |
|--------|---------|
| `luau_bytecode.py` | Bytecode parser |
| `luau_static.py` | Static analyzer |
| `luau_worker.py` | Worker subprocess |

## Shared

| Módulo | Función |
|--------|---------|
| `config.py` | Config schema |
| `shared_cache.py` | A7 shared-string cache |
| `console.py` | Stdin/stdout console |
| `scan_title.py` | Title fetcher |
| `player_probe.py` | Player state checker |
| `node_store.py` | Nodes DB with eviction |
| `players.py` | Player tracker |

## Flujo general

```
User runs: python -m rakbot mass --mm2 --mass-cookies 10

__main__.py argparse → mass.py MassRunner.run()
                                │
                                ▼
                 MassRunner._loop spawns 10 subprocesses
                                │
                                ▼
Each subprocess: python -m rakbot.mass_worker --mm2 --place-id 142823291
                                │
                                ▼
                 mass_worker.py:
                  1. Read cookie from stdin
                  2. RobloxBootstrap(cred, proxy_pool)
                  3. authenticate()
                  4. prepare(place_id)
                  5. GameClient(info) in thread
                  6. (--mm2) mm2_client.Session().run()
                                │
                                ▼
                 GameClient connects UDP, replicates world
                                │
                                ▼
                 Session.tick() every 50ms:
                  - find Coin_Server nearest
                  - mm2_wire.getcoin_payload(coin)
                  - transport.send(payload)
                                │
                                ▼
                 On CoinCollected event: session.on_coin_collected()
                 On candy threshold 600: mm2_wire.opencrate_payload()
                 EmbersickleWatcher: polls Weapons.Owned every 2s
```

## Links por módulo

- [[01-bootstrap-flow]]
- [[02-replication-reader]]
- [[03-persistent-client]]
- [[04-game-client]]
- [[05-schema-isr]]
- [[06-physics-quantize]]

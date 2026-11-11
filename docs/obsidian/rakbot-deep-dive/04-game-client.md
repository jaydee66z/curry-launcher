# Rakbot — GameClient

`rakbot/game_client.py` es la high-level API que combina `PersistentTransport` + `Inspector` + lifecycle. Es lo que usás en vez de instanciar cada módulo a mano.

## API esperada

Signature (reversed from usage in mass_worker.py and brainrot.py):

```python
class GameClient:
    def __init__(self, info: ConnectionInfo, *,
                 commands: queue.Queue = None,
                 on_player: callable = None,
                 on_character: callable = None,
                 on_command: callable = None,
                 on_brainrots: callable = None,
                 scan_once: bool = False):
        """info comes from RobloxBootstrap.prepare()"""
    
    def run(self, duration: float = None) -> dict:
        """Blocking loop: UDP recv, inspector.push, trigger callbacks.
        Returns a result dict with 'state', 'elapsed_seconds', etc."""
    
    def chat(self, message: str):
        """Send chat message"""
    
    @property
    def scan_complete(self) -> bool:
        """For --only-best scanner mode"""
```

## Attributes que podemos leer

Basado en usage patterns:
- `client.inspector` o `client._inspector` — la instancia de Inspector
- `client.transport` o `client._transport` — la PersistentTransport
- `client._thread` — el thread background que corre `run()`

**Al despertar, verificar** con:
```bash
grep -n "self\." rakbot/game_client.py | head -40
```

## Callbacks disponibles

### `on_player(player: dict)`

Se llama cuando un player se joinea al server:
```python
{
    "user_id": 12345,
    "name": "SomeUser",
    "display_name": "SomeUser",
    "character": True/False,
}
```

### `on_character(character: dict)`

Cuando el char local spawnea:
```python
{
    "character_spawned": True,
    "position": (x, y, z),
    ...
}
```

### `on_command(result: dict)`

Resultado de comandos chat-based.

### `on_brainrots(snapshot: dict)`

Scanner-specific para Steal a Brainrot.

## Para MM2 farm, lo que necesitamos del GameClient

1. **`inspector`** — para iterar nodes, encontrar Coin_Server, llamar `inspector.event_value` listener
2. **`transport`** — para `transport.send(payload)` de nuestros GetCoin
3. **`on_character`** callback — para saber cuándo HRP está spawned y arrancar la Session

Esquema:
```python
session = None

def _on_char(evt):
    nonlocal session
    if evt.get("character_spawned") and session is None:
        session = Session(inspector=client.inspector,
                          transport=client.transport)
        session.run_in_thread()

client = GameClient(info, on_character=_on_char)
client.run(duration=3600)  # 1 hour
```

## Problemas comunes

### 1. `inspector` no se popula hasta que llega JoinData

El UDP handshake + JoinData puede tomar 2-10s. Antes, `inspector.nodes` está vacío. Nuestra Session.tick() handle esto — si `_hrp_position()` devuelve None, return silent.

### 2. `transport.send` puede bloquear si socket buffer lleno

Default `socket.send` es blocking. Si enviamos 20 packets/sec y el socket buffer está full, `send` wait. No es crisis, pero bajo load alto puede retrasar.

Mitigación: `socket.setblocking(False)` en `NativeClient`. Rakbot probablemente ya lo hace.

### 3. `client.run()` corre en main thread → bloquea

Si llamás `client.run(duration=3600)` el main thread stays stuck 1 hora. Nuestra Session necesita correr PARALELA.

Fix en `mass_worker.run_mm2_farm`: run client en thread daemon, Session en main:

```python
import threading
t = threading.Thread(target=lambda: client.run(duration=args.duration), daemon=True)
t.start()
# esperar join
while client.inspector.own is None and time.monotonic() < deadline:
    time.sleep(0.1)
# arrancar session en main
session.run(duration=remaining, dry_run=args.mm2_dry_run)
```

### 4. GameClient's own event listeners sobrescriben nuestros

Si `GameClient` ya tiene `inspector.event_value = my_handler`, cuando nosotros hacemos `inspector.event_value = wrapped_handler` lo sobrescribimos.

Fix: wrap, no replace:
```python
orig_handler = inspector.event_value
def chain(name, key, args):
    my_logic(name, key, args)  # nuestra lógica
    orig_handler(name, key, args)  # delegar al original
inspector.event_value = chain
```

Ya lo hacemos así en `mass_worker.run_mm2_farm`.

## Lifecycle completo

```
1. bootstrap.prepare(place_id) → ConnectionInfo (incluye serverIP, port, join_script, session_ticket)
2. GameClient(info) → open socket, send RakNet OpenConnectionRequest
3. Server responds with OpenConnectionReply
4. ConnectedClient handshake (ChaCha key exchange)
5. ClientReplicator loads schema → inspector.schema populated
6. JoinData packet → inspector.new_many() creates initial nodes
7. Player.CharacterAdded event → inspector.own set
8. Character spawn → HRP node created in inspector.nodes
9. RunService.Heartbeat (ours): Session.tick() picks coins + fires
10. Server ticks → ChangedProperty / Event packets → inspector decodes
11. CoinCollected event → session.on_coin_collected() → counters++
12. STOP_AT_50 reached → session goes idle but still inspects
13. CoinsStarted → new round → session.on_coins_started() resets
14. Eventually duration expires → client.run() returns → mass_worker exits
```

## Links

- [[00-overview]]
- [[02-replication-reader]]
- [[03-persistent-client]]
- [[../mm2-port/03-session-loop]]

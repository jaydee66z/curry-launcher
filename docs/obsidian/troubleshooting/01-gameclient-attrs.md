# Troubleshooting — `GameClient has no inspector`

## Síntoma

En logs del subprocess:
```json
{"event": "error", "message": "GameClient has no inspector (schema missing)."}
```

o:
```json
{"event": "error", "message": "GameClient has no transport."}
```

## Causa

Mi código `mass_worker.run_mm2_farm` hace:

```python
inspector = getattr(client, 'inspector', None)
transport = getattr(client, 'transport', None)
```

**Asumí** que los attributes se llaman así. Si `game_client.GameClient` los expone con otro nombre (ej. `_inspector`, `replicator`, `_transport`, `conn`), esos getattr devuelven None.

## Fix (5 minutos)

### Paso 1 — encontrar los nombres reales

```bash
grep -n "self\." rakbot/game_client.py | head -40
```

Buscar líneas que crean attributes relevantes:
```
self.inspector = Inspector(...)      ← o
self._inspector = Inspector(...)     ← probable
self.replicator = Inspector(...)     ← alternativa

self.transport = PersistentTransport(...)  ← o
self._transport = PersistentTransport(...)
self.conn = PersistentTransport(...)
```

### Paso 2 — fix en `mass_worker.py:run_mm2_farm`

Reemplazar:
```python
inspector = getattr(client, 'inspector', None)
transport = getattr(client, 'transport', None)
```

Por los nombres reales. Ej:
```python
inspector = client._inspector
transport = client._transport
```

### Paso 3 — rerun N1

```bash
C:/Python312/python.exe -m rakbot.mass_worker --mm2 --mm2-dry-run --place-id 142823291 --duration 60
```

Si ahora emite `dry_send` events → **fix OK**.

## Fix robusto (recomendado)

En vez de asumir un nombre, probar varios:

```python
# En mass_worker.run_mm2_farm:
inspector = None
for attr in ('inspector', '_inspector', 'replicator', 'reader'):
    inspector = getattr(client, attr, None)
    if inspector is not None:
        break

transport = None
for attr in ('transport', '_transport', 'conn', 'client'):
    transport = getattr(client, attr, None)
    if transport is not None and hasattr(transport, 'send'):
        break
```

Esto hace el código resiliente a renames futuros.

## Alternativa si no exponen

Si `GameClient` NO expone ninguno:
- Fork de `game_client.py` que agregue `self.inspector = ...` como attribute pública
- O construir Inspector + PersistentTransport desde `info` directamente, sin GameClient

Ejemplo del construct manual:
```python
from rakbot.replication import Inspector
from rakbot.persistent_client import PersistentTransport
from rakbot.schema import Schema
from rakbot.native_client import NativeClient

# info viene de bootstrap.prepare()
schema = Schema.from_info(info)
native = NativeClient.from_info(info)
transport = PersistentTransport(native)
inspector = Inspector(schema, info.account.user_id)

# Loop: recv packets, push them to inspector
while running:
    packet = transport.recv(timeout=0.1)
    if packet:
        inspector.push(packet)
    # ... session.tick() can run in parallel
```

Esto evita la dependencia en `GameClient` pero es más código.

## Verificación

Tras el fix, dry-run debería producir:

```json
{"event": "connection_info_ready", ...}
{"event": "character", ...}         ← character joined
{"event": "mm2", "dry_send": ...}   ← payloads generados
...
```

Si todavía falla con un error distinto → ver otros docs de troubleshooting.

## Links

- [[00-index]]
- [[../rakbot-deep-dive/04-game-client]]

# Rakbot — schema + ISR (Instance State Record)

`rakbot/schema.py` describe las clases, properties, events que el server replica. Deriva del JoinData handshake.

`rakbot/isr.py` decodea ISR packets — deltas incrementales de propiedades (más eficientes que ChangedProperty individual).

## Schema class

```python
class Schema:
    classes: list[dict]        # [{name: str, properties: list[dict]}]
    properties: list[dict]      # [{name: str, type: int}]
    events: list[dict]          # [{class_id: int, name: str, arguments: list}]
    enums: list                 # Enum definitions
    string_tables: list[list[str]]  # Shared string pools
    dynamic_types: list        # Dynamic resource types
```

### `Schema.classes[cid]`

Describe una clase:
```python
{
    "name": "Part",
    "properties": [
        {"name": "Name", "type": 2},        # String
        {"name": "CFrame", "type": 27},     # CFrame
        {"name": "CanCollide", "type": 1},  # Bool
        # ... etc
    ]
}
```

Index `cid` es el referenciado en packets `0x02` (NewInstance) y en `event.class_id`.

### `Schema.events[eid]`

Describe un event:
```python
{
    "class_id": idx_del_class_que_fires,   # ej. RemoteEvent class
    "name": "RemoteOnReceive",              # cómo el server llama al event
    "arguments": [
        {"type": 29},  # single variant array
    ]
}
```

`eid` es el que va en packets `0x07` (Event) como u16.

### `Schema.properties[pid]`

```python
{"name": "Position", "type": 19}
```

`pid` es el que va en packets `0x03` (ChangedProperty).

### `Schema.string_tables`

Shared pool de strings comunes:
- Table 0: usado por ContentId
- Table 1: usado por OptimizedString (encoding kind=49)

Las usa el Inspector para decodear "este string es el elemento N del table K".

## ISR (Instance State Record)

Packets opcode `0x12` (?) o dentro de item `0x?` (verificar). Son snapshots incrementales:

```python
# Estructura (rakbot.isr.decode):
{
    "frame": int,               # frame number (monotonic)
    "updates": [
        (key, cid, frame, {prop_name: value, ...}),
        ...
    ],
    "skipped": {reason: count}  # metrics
}
```

Más eficiente que N packets `0x03` individuales. Nuestro `Inspector.push_isr` lo procesa.

## Schema derivation

El schema se arma en el bootstrap handshake:

```
1. NativeOpen hace 2-step open handshake
2. Server envía SchemaBlob (o similar) encrypted
3. Rakbot decodifica → Schema object
4. Schema se queda guardado en el Inspector
```

**Importante**: cada place tiene schema distinto. MM2 vs Steal an Egg tienen clases/events diferentes.

**En runtime**: si el schema cambia (Nikilis deployed un update), el handshake re-negotiates. Rakbot debería reconectar.

## Cómo encontrar un event específico

Ej. "¿dónde está `RemoteEvent.OnClientEvent`?":

```python
for idx, ev in enumerate(inspector.schema.events):
    cls = inspector.schema.classes[ev['class_id']]['name']
    if cls == 'RemoteEvent' and 'OnReceive' in ev['name']:
        print(f"Event id {idx}: {ev['name']} with args {[a['type'] for a in ev['arguments']]}")
```

Esto es lo que hace nuestro `mm2_wire.find_remote`.

## Debug: dumpear todo el schema

```python
import json
with open('schema_dump.json', 'w') as f:
    json.dump({
        'classes': inspector.schema.classes,
        'events': [{'cls': inspector.schema.classes[e['class_id']]['name'],
                    'name': e['name'],
                    'args': [a['type'] for a in e['arguments']]}
                   for e in inspector.schema.events],
    }, f, indent=2)
```

Útil para troubleshoot payload issues.

## Variations entre placeIds

Para los 3 games de interés:

| Game | Place ID | Notable events |
|------|----------|----------------|
| MM2 | 142823291 | `GetCoin`, `CoinCollected`, `OpenCrate`, `KnifeStabbed`, `Shoot` |
| Steal an Egg | 107778070777162 | Networking packages (event-driven) |
| Steal a Brainrot | 109983668079237 | `CommunicationRoute`, `__ReplicatorInternal.RemoteEvent` |

Nuestro port MM2 asume específicamente la schema de MM2. NO generalizable sin rewriting.

## Links

- [[00-overview]]
- [[02-replication-reader]]
- [[04-game-client]]
- [[../mm2-port/02-wire-protocol]]

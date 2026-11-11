# Troubleshooting — schema mismatch (payload empty)

## Síntoma

En dry-run:
```json
{"event": "mm2", "dry_send": null}   # never fires
```

O logs muestran que `find_remote` siempre devuelve `(None, None)`.

## Causa

`mm2_wire.find_remote` escanea `inspector.schema.events` buscando:

```python
for event in inspector.schema.events:
    if event['class_id'] == class_id_of_RemoteEvent and event['name'] == 'RemoteOnReceive':
        return match
```

Si la schema del MM2 real usa un nombre distinto (`'OnClientInvoke'`, `'RemoteOnEventSent'`, etc), nunca matchea → None.

## Diagnóstico

Agregar temporariamente al top de `mm2_wire.find_remote`:

```python
def find_remote(inspector, path, *, class_name):
    import sys
    sys.stderr.write(f"\n=== find_remote(path={path}, class={class_name}) ===\n")
    sys.stderr.write(f"schema has {len(inspector.schema.events)} events\n")
    for i, ev in enumerate(inspector.schema.events):
        cls = inspector.schema.classes[ev['class_id']]['name']
        sys.stderr.write(f"  [{i}] class={cls} name={ev['name']} args={[a['type'] for a in ev['arguments']]}\n")
    sys.stderr.flush()
    # ... resto del código
```

Al correr dry-run con `2>debug.txt`:

```bash
C:/Python312/python.exe -m rakbot.mass_worker --mm2 --mm2-dry-run ... 2>debug.txt
cat debug.txt
```

Verás todos los eventos. Identificar el que matchea pattern `RemoteEvent` → copiar nombre exacto.

## Fix

Si el nombre real es, e.g. `'OnReceive'`:

```python
# mm2_wire.py
event_name = {
    "RemoteEvent": "OnReceive",              # ← ajustado
    "RemoteFunction": "OnServerInvoke",      # ← ajustado
}[class_name]
```

## Fix automático (recomendado)

En vez de hardcodear nombres, aceptar varios:

```python
# mm2_wire.py
_EVENT_ALIASES = {
    "RemoteEvent": {"RemoteOnReceive", "OnClientEvent", "FireServer", "OnReceive"},
    "RemoteFunction": {"RemoteOnInvokeServer", "InvokeServer", "OnServerInvoke"},
}

def find_remote(inspector, path, *, class_name):
    valid_names = _EVENT_ALIASES[class_name]
    # ... rest
    for idx, ev in enumerate(inspector.schema.events):
        cls = inspector.schema.classes[ev['class_id']]['name']
        if cls == class_name and ev['name'] in valid_names:
            # ...
```

## Verificación

Tras el fix:

```bash
C:/Python312/python.exe -m unittest rakbot.tests.test_mm2_wire.TestRemoteDiscovery -v
```

Los tests deberían seguir pasando (usan los nombres del fixture).

Y en dry-run, `dry_send` events deberían aparecer con `bytes > 0`.

## Verificación byte-level

Si querés comparar bytes contra un fire real de Main.luau:

1. Correr Main.luau en executor con hook:
   ```lua
   local orig = GetCoin.FireServer
   GetCoin.FireServer = function(self, ...)
       local args = {...}
       print("[sniff]", game:GetService("HttpService"):JSONEncode(args))
       return orig(self, ...)
   end
   ```
2. En el executor, verás los bytes raw del packet UDP (requires mcp__roblox-mcp o similar). 
3. Comparar los primeros 8-16 bytes con lo que emite Python dry_run.

Si matchean primeros 8 bytes (`0x83 0x07` + wire_guid prefix) → ya casi.
Si difieren → hay un opcode mal.

## Links

- [[00-index]]
- [[../mm2-port/02-wire-protocol]]
- [[../api-reference/02-mm2-remotes]]

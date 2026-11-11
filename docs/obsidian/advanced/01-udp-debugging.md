# Advanced — UDP packet debugging

> Cuando el payload parece correcto pero el server no responde.

## Herramientas

### 1. `tcpdump` / `wireshark`

Capturar tráfico UDP crudo:

```bash
# En VPS
sudo tcpdump -i eth0 -w capture.pcap udp port 53640
# Hacer 1 fire GetCoin
# Ctrl+C
# Download capture.pcap, abrir en Wireshark
```

El payload está encriptado (ChaCha20). Pero sí podés ver:
- Tamaño del packet (debería matchear tus bytes + ~30 bytes de header UDP + crypto overhead)
- Frecuencia (confirmar que mandás 1 packet por send())
- Si el server responde con packet distinto después de cada send (ack vs data)

### 2. Instrumentar `PersistentTransport.send`

Agregar log temporario:

```python
# rakbot/persistent_client.py (TEMPORAL — remover después)

def send(self, payload):
    import sys, binascii
    sys.stderr.write(f"\n[tx] {binascii.hexlify(payload)[:40]}... ({len(payload)}B)\n")
    sys.stderr.flush()
    return self._orig_send(payload)
```

Correr con `2>>debug.txt` para capturar.

### 3. Comparar con Main.luau remote spy

Si el executor tiene remote-spy, interceptar `GetCoin.FireServer`:

```lua
-- Hook
local function hook(remote, name)
    local orig = remote.FireServer
    remote.FireServer = function(self, ...)
        print("[spy] " .. name, game:GetService("HttpService"):JSONEncode({...}))
        return orig(self, ...)
    end
end

hook(game.ReplicatedStorage.Remotes.Gameplay.GetCoin, "GetCoin")
```

Esto dumpea los args, no los bytes raw. Para bytes raw:
- Usar `mcp__roblox-mcp__remote-spy` con `capture_arguments=true` y `limit=5`
- O leer el traffic UDP con un executor que lo exponga (Synapse X Pro)

### 4. Diff byte-by-byte

Tener side-by-side:
- Luau fire → bytes capturados = `L1 L2 L3 ... L30`
- Python fire → bytes esperados = `P1 P2 P3 ... P30`

Comparar byte a byte:
```python
luau_bytes = bytes.fromhex("830701...")
python_bytes = bytes.fromhex("830701...")

for i, (l, p) in enumerate(zip(luau_bytes, python_bytes)):
    if l != p:
        print(f"Diff at byte {i}: luau={l:02x}, python={p:02x}")
```

Si solo diferen en 1-2 bytes → probablemente invocation_id o timestamp.
Si diferen en opcodes al inicio → estructura mal.

## Debugging por error

### "sever accepts but no response"

Hipótesis: server NO procesa tu payload por deserialización falla.

Debug:
1. Agregar Marcelino item antes y después del Event:
   ```
   0x83 0x04 0xAA 0xBB 0xCC 0xDD   # Marker con 4 bytes (0x04 opcode)
   0x07 ...event body...
   0x04 0xEE 0xFF 0x11 0x22         # Otro marker
   0x00                              # End
   ```
2. Si el server acknowledges hasta el primer marker pero nada después → el event body está mal
3. Si acknowledges nada → el first marker está mal (opcode error)

### "disconnection después de fire"

Hipótesis: server detecta payload inválido y boots.

Debug:
1. Fire 1 payload, luego recv por 500ms:
   ```python
   transport.send(payload)
   for _ in range(10):
       p = transport.recv(timeout=0.05)
       if p:
           print(f"got response: {p[:20].hex()}")
           break
   ```
2. Si recv timeouts → no response (silent accept/ignore)
3. Si recv devuelve packet con opcode disconnect (~0x15 o similar) → rechazado

## Common bugs encontrados en debugging similar

### Bug 1: little vs big endian

Schema event_id es u16 `<H` (little endian). Si accidentalmente usás `>H`, el server lee event_id erróneo → dispara evento incorrecto o rejects.

### Bug 2: varuint off-by-one

`varuint(0)` = `b'\x00'` (1 byte). Fácil confundirse y escribir `b'\x01\x00'` si venís de otro protocol.

### Bug 3: tipo de variant wrong

`variant_string("x")` = `b'\x02' + varuint(1) + b'x'`. Si olvidás el type byte `\x02`, el server interpreta el len byte como type → caos.

### Bug 4: falta terminator 0x00

El variant_array debe terminar en `\x00`. Si no → server espera más variants → packet truncated error.

### Bug 5: wire_guid con scope 0

`scope >= 1` requerido. Si tus guids locales son `(0, N)` → el server rechaza silencioso.

## Quick checklist cuando no funciona

- [ ] Bytes empezan con `0x83 0x07`?
- [ ] wire_guid tiene scope ≥ 1?
- [ ] Event_id es el correcto para el class + name?
- [ ] Variants tienen type byte prefix?
- [ ] Array termina con 0x00?
- [ ] invocation_id (si RemoteFunction) es zigzag varuint?
- [ ] inspector.own populated (no None)?
- [ ] Payload size razonable (20-100 bytes típico)?

Si todos ✅ y aún falla → bug probable en `physics.py` o en el handshake ChaCha nonce. Más profundo.

## Links

- [[../mm2-port/02-wire-protocol]]
- [[../rakbot-deep-dive/06-physics-quantize]]
- [[../troubleshooting/06-pickup-failed]]

# MM2 Port — wire protocol (byte-level)

## Resumen

Rakbot transporta packets UDP cifrados con ChaCha20-Poly1305. Encima del cifrado, hay un formato de aplicación nativo 0.744 que divide cada packet en items. Nos interesan 2 opcodes de item:

| Opcode | Función |
|--------|---------|
| `0x02` | NewInstance (de servidor a nosotros) — Inspector decodea |
| `0x03` | ChangedProperty (de servidor a nosotros) — Inspector decodea |
| `0x07` | **Event** (bidireccional — lo usamos para fire remotes) |

El packet entero empieza con `0x83` = "Data packet". Un packet típico de fire es **un solo item Event**:

```
packet = 0x83 | 0x07 | <event body> | 0x00
         ───────────────────────────────────
         Data   Event    body         term
```

## Event body — general

```
<wire_guid(target_instance)>       # 1-5 bytes scope + 4 bytes random32
<u16 event_id>                     # schema index
[varuint(invocation_id * 2)]       # ONLY RemoteFunction (type 10 arg)
<wire_guid(inspector.own)>         # player instance ref (type 28 arg)
<varuint(N)>                       # variant count
<variant_1>
<variant_2>
...
<variant_N>
0x00                               # list terminator
```

## `wire_guid(key)` — serializa una referencia a instancia

```python
def wire_guid(value):
    # value = (scope: int ≥ 1, id: int 0..0xffffffff)
    return varuint(value[0]) + struct.pack('<I', value[1])
```

- `varuint(scope)` → LEB128 unsigned
- `<I` → little-endian u32

**Importante**: `scope = 0` es ilegal. En tests se usan tuples `(1, N)` para GUIDs locales.

## `varuint(n)` — LEB128

```python
def varuint(value):
    output = bytearray()
    while value >= 128:
        output.append((value & 127) | 128)   # 7 bits + continuation
        value >>= 7
    output.append(value)
    return bytes(output)
```

Ejemplos:
- `varuint(0)` → `b'\x00'`
- `varuint(127)` → `b'\x7f'`
- `varuint(128)` → `b'\x80\x01'`
- `varuint(300)` → `b'\xac\x02'`

## Variant kinds relevantes

Decodeados en `replication.Inspector.value()`:

| Kind byte | Tipo | Encoding |
|-----------|------|----------|
| `0x02` (2) | String | `varuint(len) + utf8_bytes` |
| `0x0a` (10) | ZigzagInt | `varuint(signed_value * 2 ^ signed_value >> 63)` |
| `0x1c` (28) | Instance ref | `wire_guid(key)` |
| `0x1d` (29) | VariantArray | `varuint(count) + variants + 0x00` |
| `0x13` (19) | Vector3 | `3 × float32` |
| `0x1b` (27) | CFrame | `12 bytes position + 1 byte rotation_code + optional 6 bytes` |

Para GetCoin solo necesitamos `0x1c` (Instance) y la outer `variant_array`.
Para OpenCrate solo necesitamos `0x02` (String) y la outer `variant_array`.

## GetCoin:FireServer(coin) — payload exacto

```
0x83                                # Data packet
0x07                                # Event item
wire_guid(remote_key)               # the GetCoin RemoteEvent instance
<u16 event_id>                      # from schema (RemoteOnReceive, [29])
wire_guid(inspector.own)            # LocalPlayer ref
varuint(1)                          # 1 variant in the array
0x1c                                # kind = Instance
wire_guid(coin_server_key)          # the Coin_Server Part
0x00                                # variant array terminator
```

Mínimo: ~20 bytes
Máximo: ~30 bytes (depende de varuint sizes)

## OpenCrate:InvokeServer(box, type, currency) — payload exacto

```
0x83                                # Data packet
0x07                                # Event item
wire_guid(remote_key)               # OpenCrate RemoteFunction instance
<u16 event_id>                      # from schema (RemoteOnInvokeServer, [10, 28, 29])
varuint(invocation_id * 2)          # zigzag (type 10)
wire_guid(inspector.own)            # LocalPlayer ref (type 28)
varuint(3)                          # 3 variants in the array
0x02 + varuint(len) + b'Halloween2026Box'
0x02 + varuint(len) + b'MysteryBox'
0x02 + varuint(len) + b'Candies2026'
0x00                                # terminator
```

Mínimo: ~60 bytes

## Referencia: heli_wars.team_request

Nuestro código sigue este patrón **EXACTO**. Viene de `rakbot/heli_wars.py:17-63`:

```python
payload = (b'\x83\x07'
           + wire_guid(remote)
           + struct.pack('<H', candidates[0])     # event_id u16
           + varuint(invocation_id * 2)           # zigzag (type 10)
           + wire_guid(inspector.own)             # player (type 28)
           + varuint(2)                           # 2 variants
           + b'\x02' + string('JoinTeam')         # variant 1: string
           + b'\x02' + string(team_name)          # variant 2: string
           + b'\0')                               # terminator
```

Nuestro `invoke_remote_function` es idéntico pero parametrizando los variants.

## Verificación de tests

12 tests en `rakbot/tests/test_mm2_wire.py` verifican:

- `test_variant_instance_shape` → `b'\x1c' + wire_guid(key)` exacto
- `test_variant_string_shape` → `b'\x02' + varuint(len) + utf8` exacto
- `test_variant_array_terminator` → termina en `0x00`
- `test_getcoin_header_opcodes` → empieza en `b'\x83\x07'`
- `test_opencrate_header_opcodes` → empieza en `b'\x83\x07'`
- `test_find_getcoin` → path resolver encuentra el remote
- `test_find_opencrate` → idem para RemoteFunction
- `test_missing_remote` → devuelve `(None, None)` sin crash
- `test_getcoin_contains_coin_guid` → el coin ref está en el payload
- `test_opencrate_contains_strings` → los 3 strings están embebidos
- `test_opencrate_increments_invocation` → invocation_id distinto → payload distinto
- `test_variant_array_empty` → `varuint(0) + 0x00`

**12/12 pass** (verificado con `python -m unittest rakbot.tests.test_mm2_wire`).

## Qué NO está verificado

- **Schema real de MM2**: no sé con certeza qué event_id corresponde a `RemoteOnReceive` para un RemoteEvent genérico en la build actual. `find_remote` asume que es el único con `class_id` apuntando a `RemoteEvent` y `name='RemoteOnReceive'`. Si hay múltiples, devuelve `(key, None)`.
- **Que el server accepte el payload**: hasta no fire real, nadie sabe. Dry-run no envía UDP.
- **Que CoinCollected sea `RemoteEvent.OnClientEvent`**: lo deduje de v0.14 del Main.luau pero schema server-side puede variar.

## Links

- [[00-status]]
- [[01-architecture]]
- [[03-session-loop]]

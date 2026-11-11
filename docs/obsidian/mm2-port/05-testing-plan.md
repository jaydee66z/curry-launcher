# MM2 Port — plan de testing

## Niveles de verificación

### N0 — Unit tests (ya ejecutado ✅)

```bash
cd "C:\Users\Administrator\Documents\Curry Launcher\curry-launcher"
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m unittest rakbot.tests.test_mm2_wire -v
```

**Esperado**: `Ran 12 tests in 0.001s / OK`.

Ya verificado. Confirma que los encoders producen bytes con la estructura esperada (opcodes `0x83 0x07`, variants con kind correcto, strings embebidas, invocation_id incrementa).

### N1 — Dry-run (correr al despertar, zero AC risk)

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot mass --mass-cookies-path cookies.txt --mass-cookies 1 --place-id 142823291 --duration 60
```

**Nota**: este comando aún NO tiene `--mm2`. Rakbot `mass` no expone todavía los flags. Hay que agregarlos al CLI. Workaround rápido:

```bash
# Usar el worker directamente
echo '{"cookie": "LA_COOKIE_DE_VERIFICACION"}' | \
   C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot.mass_worker \
     --mm2 --mm2-dry-run --place-id 142823291 --duration 60
```

**Esperado — líneas JSON en stdout**:
```json
{"event": "authenticated", "user_id": 123456789, "proxy_pool": true}
{"event": "connection_info_ready", "user_id": 123456789, "place_id": 142823291, ...}
{"event": "character", ...}
{"event": "mm2", "dry_send": {"bytes": 23, "head": "8307010101..."}}
{"event": "mm2", "dry_send": ...}
...
```

Si ves `dry_send` events → **phase 1 funciona end-to-end**.

Si ves `GameClient has no inspector` → los nombres de atributos en `game_client.py` no coinciden con lo que asumí. Fix: leer `game_client.py` y ajustar los dos `getattr` en `mass_worker.run_mm2_farm`.

Si ves `"error": "Timed out waiting for inspector.own"` → el join funcionó pero el replicator no popula `inspector.own` en 60s. Posible causa: captcha_join, VIP server required, place requires age verification.

### N2 — Live fire con 1 cuenta (verificación real)

**Solo correr si N1 pasó**. Remueve `--mm2-dry-run`:

```bash
echo '{"cookie": "LA_COOKIE"}' | \
   C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot.mass_worker \
     --mm2 --place-id 142823291 --duration 120
```

**Esperado**:
```json
{"event": "mm2", "pickup": {"type": "Candy", "round": 1, "life": 1}}
{"event": "mm2", "pickup": {"type": "Candy", "round": 2, "life": 2}}
...
```

Si **ningún pickup fire** pero sí emite el payload: hay dos opciones:
- (a) Server rechaza silencioso por distancia → necesitamos phase 2 (navegación)
- (b) Schema mismatch → el server interpreta mal los bytes

Diferenciar: capturar un fire de Main.luau real con Wireshark, comparar primeros 8 bytes contra lo que emitimos.

Si **pickups llegan sin movimiento**: 🎉 **phase 2 no es necesaria**, saltamos a scale.

### N3 — Sanity con 2-3 cuentas (una vez N2 funciona)

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot mass \
   --mass-cookies-path cookies.txt --mass-cookies 3 --mm2 --place-id 142823291 --duration 180
```

Esto requiere exponer `--mm2` en el CLI de `rakbot mass` (ver `rakbot/__main__.py`). Si no está, pendiente para mañana:

```python
# rakbot/__main__.py, dentro del parser de 'mass':
auth.add_argument('--mm2', action='store_true',
                  help='Run MM2 pure-Python farm')
auth.add_argument('--mm2-dry-run', action='store_true',
                  help='Log payloads without sending')
```

Y en el call a `MassRunner`:
```python
MassRunner(credentials, place_id=args.place_id, ...,
           mm2=args.mm2, mm2_dry_run=args.mm2_dry_run).run()
```

### N4 — Scale 10 cuentas

```bash
... --mass-cookies 10 --duration 600
```

Observar:
- RAM del PC (1 subprocess = ~30-50 MB)
- CPU (loop @ 20Hz × 10 = 200 ticks/sec, trivial)
- DataImpulse dashboard (tráfico GB consumido)
- Logs por cuenta: cuántos pickups, boxes, errores

### N5 — Scale 100 cuentas

```bash
... --mass-cookies 100 --duration 3600
```

Requerimientos:
- 32 GB RAM mínimo (overhead Python subprocess ≈ 50 MB × 100 = 5 GB + OS)
- CPU 8 cores recomendado
- DataImpulse: ~0.5 GB / 100 cuentas / hora

### N6 — Scale 500+ cuentas (1 VPS)

Mover a VPS Linux 16 GB RAM, 8 cores. Cada account consume 5-10 MB en Linux (sin Roblox Player).

## Red flags que detener el test inmediatamente

- **Rate limit en bulk (HTTP 429 en auth)**: cookies banned, detener y rotar IPs
- **Captcha_join universal**: provider de cookies está marcado, no usar ese batch
- **Session worker crashea en loop**: bug Python, revisar logs
- **DataImpulse 2 GB se consume en <5 min**: hay error en el routing (está mandando game traffic al proxy — no debería)

## Rollback a Luau executor

Si el port Python falla y necesitas ingreso inmediato, reactivá el Main.luau executor:

```bash
# El Main.luau está intacto en scripts/mm2-candy-farm/Main.luau
# Los commits del Luau no fueron borrados.
# Ejecutá con Synapse/Krnl en el cliente Roblox oficial.
```

Hasta 10 cuentas en 1 PC con 16 GB. Lento pero funciona.

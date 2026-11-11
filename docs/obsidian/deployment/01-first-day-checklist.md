# Deployment — primer día checklist

> Al despertar, seguí este orden exacto. Cada paso ~5-15 min.

## Pre-check (10 min)

- [ ] Abrir obsidian vault: `docs/obsidian/mm2-port/00-status.md` → leer TL;DR
- [ ] Verificar que `cookies.txt` tiene 9 cookies y está gitignored:
  ```bash
  wc -l cookies.txt
  git check-ignore cookies.txt
  ```
- [ ] Verificar `proxies.txt` 2000 líneas:
  ```bash
  wc -l proxies.txt
  grep -c "gw.dataimpulse.com" proxies.txt
  ```
- [ ] Verificar `MM2_DISCORD_WEBHOOK_URL` env var (si querés webhook):
  ```bash
  echo %MM2_DISCORD_WEBHOOK_URL%
  ```

## N0 — Tests unitarios (5 min)

```bash
cd "C:\Users\Administrator\Documents\Curry Launcher\curry-launcher"
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m unittest discover -s rakbot/tests -v
```

**Esperado**: `Ran 28 tests in X.Xs / OK`.

Si falla:
- Revisar output del test que rompió
- No cambiar el código del farm — fix solo el test
- Si es un problema de imports → `pip install cryptography`

## N1 — Dry-run 1 cuenta (10 min)

```bash
# Usar primera cookie de cookies.txt directamente por stdin
head -5 cookies.txt | tail -1 > /tmp/first_cookie.txt
# (En Windows PS):
Get-Content cookies.txt | Where-Object { $_ -match '^_\|' } | Select-Object -First 1 > first.txt

# Luego:
powershell -Command '{"cookie": "'(Get-Content first.txt)'"}' | C:/Python312/python.exe -m rakbot.mass_worker --mm2 --mm2-dry-run --place-id 142823291 --duration 90
```

**Esperado**:
```json
{"event": "authenticated", "user_id": 123456789, "proxy_pool": true}
{"event": "connection_info_ready", ...}
{"event": "character", ...}
{"event": "mm2", "dry_send": {"bytes": 23, "head": "830701..."}}
...
```

Si ves `dry_send` → **phase 1 end-to-end funciona**. GO a N2.

Si ves `"error": "GameClient has no inspector"`:
1. `cat rakbot/game_client.py | head -50` → encontrar qué attribute expone
2. Reemplazar `getattr(client, 'inspector', None)` por el nombre real en `mass_worker.run_mm2_farm`
3. Re-run N1

Si ves `"error": "Timed out waiting for inspector.own"`:
- Posible captcha_join en esa cookie
- Probá con otra cookie: `head -3 cookies.txt | tail -1`

## N2 — Live fire 1 cuenta (15 min)

SOLO si N1 pasó. Remové `--mm2-dry-run`:

```bash
# Con la MISMA cookie que funcionó en N1
echo '{"cookie": "LA_COOKIE"}' | C:/Python312/python.exe -m rakbot.mass_worker --mm2 --place-id 142823291 --duration 300
```

**Esperado tras 1-2 min** (una vez el round arranca):
```json
{"event": "mm2", "pickup": {"type": "Candy", "round": 1, "life": 1}}
{"event": "mm2", "pickup": {"type": "Candy", "round": 2, "life": 2}}
...
```

Si **sin pickups** después de 2 min pero SÍ con `dry_send`:
- El server está recibiendo bytes pero no los acepta
- Diagnosticar en [[../troubleshooting/06-pickup-failed]]

Si pickups llegan → 🎉 **confirmado**. Pasá a N3.

## N3 — Scale 3 cuentas local (20 min)

```bash
C:/Python312/python.exe -m rakbot mass --mass-cookies-path cookies.txt --mass-cookies 3 --mm2 --place-id 142823291 --duration 600
```

10 min. Observar:
- 3 subprocesses en Task Manager
- Logs: 3 × `authenticated`, 3 × `pickup`s
- Pickups esperado: ~150 total (50/cuenta/ronda × 1-2 rondas)
- RAM total: ~200-300 MB

## N4 — Scale 9 cuentas (todas las tuyas, 30 min)

```bash
C:/Python312/python.exe -m rakbot mass --mass-cookies-path cookies.txt --mass-cookies 9 --mm2 --place-id 142823291 --duration 1800
```

30 min. Lo que debería pasar:
- 9 subprocesses, uno por cuenta
- Cada account_id va por su proxy pinned
- ~450 candies/ronda × 9 cuentas × 10-15 rondas = **40k-70k candies**
- Boxes: ~70-110 abiertas (candies / 600)
- Embersickle drops: esperado 0-1 en esta primera sesión (random)

## N5 — Decisión scale

Tras N4 exitoso, dos caminos:

### Camino A: Scale en tu PC (hasta ~30 cuentas)

Comprar 20-30 cookies más en RoCracked/NexusGen, agregar a `cookies.txt`, pero correrlas con --mass-cookies 30.

Ventaja: zero infra cost. Desventaja: tu PC bloqueada farmando.

### Camino B: Mover a VPS (recomendado para scale real)

Seguir [[../infrastructure/03-vps-setup]]. Day 2+.

## Monitoring durante N4 / scale

```bash
# Segunda terminal: tail de logs
tail -f logs.txt | grep -E "pickup|box|rare"

# Count
grep -c "pickup" logs.txt
grep -c "box_fired" logs.txt
```

## Discord webhook check

Si configuraste `MM2_DISCORD_WEBHOOK_URL`, deberías ver en tu server:
- **Embed azul "TEST"** al arranque (si tests bots reports)
- **Embed dorado/naranja** si cae Embersickle (improbable en primer día)

Si NO ves nada → env var no cargada o URL mal.

## End of day 1

Objetivos realistas:
- ✅ All 9 cookies run sin ban inmediato
- ✅ ~1000-5000 candies farmed cross-accounts
- ✅ 1-10 boxes opened
- ⚪ 0-1 Embersickles (probabilístico)
- ✅ Cero crashes en >1h run

## Links

- [[00-launch-sequence]]
- [[02-week-one-tracking]]
- [[../mm2-port/05-testing-plan]]
- [[../troubleshooting/00-index]]

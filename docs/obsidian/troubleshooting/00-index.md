# Troubleshooting — index

## Lo más común y cómo solucionarlo

| Síntoma | Causa típica | Fix inmediato | Doc relacionado |
|---------|--------------|---------------|-----------------|
| `GameClient has no inspector` | Nombres de attributos mal en game_client.py | Leer game_client.py, ajustar `getattr` en mass_worker.run_mm2_farm | [[01-gameclient-attrs]] |
| `getcoin_payload returns None siempre` | Schema mismatch | Dump inspector.schema.events, revisar event_name | [[02-schema-mismatch]] |
| `rblx-challenge-id` en logs | Captcha lock en cuenta | Resolver captcha en navegador, recargar cookie | [[03-captcha-lock]] |
| `407 Proxy Authentication Required` | Credenciales DataImpulse mal | Revisar user/pass en proxies.txt | [[04-proxy-auth]] |
| Subprocess crashea en loop | Python exception no cacheada | Capturar stderr via `2>>errors.log`, leer | [[05-subprocess-crash]] |
| Pickups sin ganar candies | Server ignora payload | Verificar wire format vs capture real | [[06-pickup-failed]] |
| `Invalid position` kick | Movimiento teleport-like | Ver phase 2 nav + rate-limit | [[07-invalid-position]] |
| Memory leak | Inspector.nodes crece sin bound | Verificar `max_nodes` arg | [[08-memory-leak]] |
| DataImpulse quota explota | Mal routing (UDP tunneled) | Confirmar que SOLO HTTPS va por proxy | [[09-proxy-explosion]] |
| Cookies banned en masa | Patrón de comportamiento detectable | Reducir scale, agregar jitter | [[10-mass-ban]] |
| Discord webhook silent | URL rota o rate limit Discord | Verificar URL, regenerar si invalid | [[11-webhook-silent]] |
| ProxyPool.enabled() False | proxies.txt vacío o path mal | Verificar `ls -la proxies.txt` | [[12-proxy-empty]] |
| Boxes se abren sin candies | OpenCrate fallback por error de lectura | Inspeccionar ProfileData replication | [[13-box-ghost]] |
| Heartbeat tick deja de actualizar | farmConn muerta silencioso | Ver self-healing en Main.luau v0.49 | [[14-heartbeat-dead]] |
| Round se cae del mapa al inicio | Hover BV no se crea a tiempo | v0.44 fix | [[15-fall-start]] |
| Static model no se queda estático | Animator se re-crea | Loop paralelo mata tracks cada 0.1s | [[16-static-model]] |
| Mapa invisible en lobby | hideLobbyVisual runs when it shouldn't | Disable en config si molesta | [[17-lobby-invisible]] |
| Rejoin loop infinito | Rescue CFrame triggers nuevo rescue | v0.34 fix (ajustar bbox check) | [[18-rejoin-loop]] |
| Collector no encuentra coins | Walkable grid filter muy estricto | WALKABLE_HARD_FILTER=false | [[19-grid-filter]] |
| Luau script loadea pero no fire | `running = false` stale | Reload manual con `running=true` | [[20-luau-stale]] |

## Diagnóstico rápido

### Paso 1 — verificar que el script está vivo

```python
# En executor
print(_G.farmDebug)
print("heartbeat age:", os.clock() - (_G.farmDebug.heartbeatTick or 0))
```

Si heartbeat age > 15s → watchdog debería rebuildear. Si no, el watchdog mismo murió.

### Paso 2 — verificar que hay coins

```python
local CS=game:GetService("CollectionService")
local n=0; for _,v in ipairs(CS:GetTagged("CoinVisual")) do if not v:GetAttribute("Collected") then n=n+1 end end
print("active coins:", n)
```

Si n=0 → estás en lobby. Si n>0 pero tripCoinID="none" → bug de filtro.

### Paso 3 — verificar network

```bash
# En VPS
curl -x "USER:PASS@gw.dataimpulse.com:10000" https://api.ipify.org
# Debería devolver una IP residencial, no la del VPS
```

### Paso 4 — verificar rakbot state

```python
# En Python session
from rakbot.bootstrap import RobloxBootstrap, Credential
from rakbot.proxy_pool import ProxyPool

pool = ProxyPool("proxies.txt")
cred = Credential(open("cookies.txt").read().splitlines()[0].strip())
bs = RobloxBootstrap(cred, account_id=0, proxy_pool=pool)
account = bs.authenticate()
print(f"user_id: {account.user_id}, username: {account.username}")
```

Si falla con BootstrapError → cookie dead o proxy mal.

## Patrones de bugs recurrentes

### Pattern 1: "funciona en test pero no en prod"

Usualmente: config distinta. Verificar:
- Mismo Python version
- Misma version de rakbot (git tag)
- Mismo path de `cookies.txt` y `proxies.txt`
- Env vars propagados correctamente

### Pattern 2: "arrancó bien y de golpe paró"

Usualmente: rate limit o ban en alguna cuenta. Verificar:
- `logs/mm2farm.log` últimos minutos antes del stop
- Si todas las cuentas pararon a la vez → network outage
- Si una por una → ban graduales

### Pattern 3: "a veces funciona, a veces no"

Race condition. Verificar:
- `inspector.own` populated antes de llamar wire encoders
- Schema loaded antes de buscar remotes
- Timer de reconnection no colisiona con join normal

## Links

- [[../mm2-port/00-status]]
- [[../mm2-port/05-testing-plan]]
- [[../errors]] (vault root)

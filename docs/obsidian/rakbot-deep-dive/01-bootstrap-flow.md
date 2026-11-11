# Rakbot — bootstrap flow

Qué pasa desde `RobloxBootstrap(cred)` hasta tener un `ConnectionInfo` listo para GameClient.

## Clases principales

```python
@dataclass
class Credential:
    value: str  # .ROBLOSECURITY cookie value
    
    def __post_init__(self):
        # strips the ".ROBLOSECURITY=" prefix if present
        # validates charset
    
    def __repr__(self): return "Credential(<redacted>)"


@dataclass
class HttpReply:
    status: int
    headers: dict
    body: bytes


class RobloxHTTP:
    def __init__(self, timeout=10, *, proxy_url=None):
        # builds urllib opener with ProxyHandler if proxy_url
    
    def request(self, url, *, credential=None, body=None, csrf=None):
        # GET or POST (POST if body), with the full Roblox header set


class RobloxBootstrap:
    def __init__(self, credential, *, http=None, account_id=None, proxy_pool=None):
        # Creates RobloxHTTP with pinned proxy if pool given
    
    def authenticate(self, cached=False):
        # GET /v1/users/authenticated → Account
    
    def prepare(self, place_id, *, attempts=3):
        # Multi-step: CSRF → /v1/join-game → parse ConnectionInfo
    
    def prepare_instance(self, place_id, job_id, *, attempts=3):
        # POST /v1/join-game-instance with job_id
    
    def prepare_vip(self, vip_link, *, attempts=3):
        # POST /v1/join-private-game with linkcode
```

## Secuencia: auth

```
cred = Credential("_|WARNING...")
bs = RobloxBootstrap(cred, account_id=0, proxy_pool=pool)
    │
    ▼
bs._http = RobloxHTTP(proxy_url="http://user:pass@gw.dataimpulse.com:10001")
    │
account = bs.authenticate()
    │
    ▼
bs._http.request("https://users.roblox.com/v1/users/authenticated", credential=cred)
    │
    ▼
urllib.request.Request → opener.open() → HTTP 200 → json parse
    │
    ▼
Account(user_id=123456789, username="Tormenta_2336", display_name="...")
```

## Secuencia: prepare (join)

```
info = bs.prepare(142823291)
    │
    ▼
1. First attempt: POST /v1/join-game  (sin CSRF)
    ▼
    Reply: 403 + x-csrf-token: XXX  (server pidiendo CSRF)
    │
    ▼
2. Second attempt: POST /v1/join-game  (con X-CSRF-TOKEN: XXX)
    ▼
    Reply: 200 + json(joinScript, serverPort, serverAddresses, etc.)
    │
    ▼
3. Parse joinScript: PlayerMetadata (username, user_id, membership, …)
    ▼
    native_open.NativeOpen(info.join_script, cred) → transport primed
    │
    ▼
ConnectionInfo(place_id, server_addresses, join_script, session_ticket, account)
```

## Errores comunes y qué significan

### `BootstrapError("Invalid session cookie format")`
Formato del cookie malo. Usualmente:
- Caracteres extraños (ej. copiado con espacios)
- Longitud excede 16384

Fix: limpiar la línea.

### `BootstrapError("Roblox rejected the session (HTTP 401)")`
Cookie expirada o cuenta hizo "sign out all sessions".

Fix: generar cookie nueva.

### `BootstrapError("Roblox requires an additional challenge")`
Captcha lock. El header `rblx-challenge-id` aparece en la respuesta.

Fix: abrir la cuenta en navegador, resolver captcha, recargar cookie.

### `BootstrapError("Destination is outside the fixed Roblox HTTPS endpoints")`
Alguien pasó una URL no en `ALLOWED_URLS`. Rakbot es strict para evitar SSRF.

Fix: revisar código que llama a `request()`.

### `NetworkUnavailable("HTTPS request failed; check network access and the configured proxy")`
TCP/HTTPS no se pudo establecer. Causas:
- Proxy caído
- DNS fail
- Firewall
- Rate limit del proxy provider

Fix: ping al proxy; retry; cambiar slot.

### `RateLimited(delay_seconds)`
HTTP 429. Rakbot rising este exception con el delay (segundos) del retry-after header.

Fix: wait + retry después del delay.

### `JoinRefused(status)`
Status 5, 6, 10 = server not accepting. Normal durante peak times.

Fix: retry a otro server (hop).

### `InstanceMismatch`
Server devolvió un JobId distinto al pedido. Raro.

Fix: retry.

## Patrones defensivos

### Pattern 1 — Cached auth

```python
account = bs.authenticate(cached=True)
```

Si llamaste `authenticate()` hace <N min, devuelve el account cacheado sin hitting la API. Usar siempre que puedas.

### Pattern 2 — Attempts loop

Rakbot internamente hace retries de 3 attempts por default. Si todas fallan → raises.

```python
try:
    info = bs.prepare(142823291, attempts=3)
except (NetworkUnavailable, RateLimited) as e:
    # Esperar + retry externo
    time.sleep(10)
    info = bs.prepare(142823291, attempts=5)
```

### Pattern 3 — Hop between servers

Si un JobId no te acepta (`JoinRefused` con status 5/6/10), prepará otro:

```python
for _ in range(10):
    try:
        info = bs.prepare_instance(place_id, next_job_id)
        break
    except JoinRefused as e:
        if e.status not in (5, 6, 10):
            raise
        next_job_id = pick_another()  # try next server
```

## Flow con el proxy integrado

```
RobloxBootstrap(cred, account_id=5, proxy_pool=pool)
    ▼
pool.url_for(5) → "http://USER:PASS@gw.dataimpulse.com:10005"
    ▼
RobloxHTTP(proxy_url=...)
    ▼
urllib.request.build_opener(NoRedirect(), ProxyHandler({...}))
    ▼
Toda request() usa el opener → CONNECT tunnel → gw.dataimpulse.com
    ▼
DataImpulse routea a IP residencial
    ▼
IP residencial talks to Roblox
```

Mismo cookie siempre sale por mismo IP (sticky), hasta que:
- cambie el account_id (nunca debería)
- se agregue/quite líneas a `proxies.txt` (cambia el `% len(lines)`)

## Links

- [[00-overview]]
- [[02-replication-reader]]
- [[../mm2-port/01-architecture]]
- [[../api-reference/00-roblox-endpoints]]

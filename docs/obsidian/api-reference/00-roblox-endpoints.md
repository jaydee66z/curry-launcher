# API Reference — Roblox endpoints usados

Todos los endpoints HTTPS que Rakbot toca. Útil para debug y entender rate limits.

## Auth / identity

| Endpoint | Método | Uso | Rate limit |
|----------|--------|-----|-----------|
| `GET /v1/users/authenticated` (users.roblox.com) | GET | Verificar que cookie es válida, obtener user_id + username | ~30/min por cookie |
| `GET /v1/users/{id}` (users.roblox.com) | GET | Info pública de user | ~60/min por IP |

## Join game

| Endpoint | Método | Uso | Rate limit |
|----------|--------|-----|-----------|
| `POST /v1/join-game` (gamejoin.roblox.com) | POST | Join a public server | ~10/min |
| `POST /v1/join-game-instance` | POST | Join a specific JobId | ~10/min |
| `POST /v1/join-private-game` | POST | Join via VIP link | ~5/min |

Rate limit 429 common si spamás joins. CSRF token required.

## Inventory / profile

Rakbot NO usa estos directamente (los lee del replicated world) pero para debug:

| Endpoint | Método |
|----------|--------|
| `GET /v2/users/{id}/inventory` (inventory.roblox.com) | Items del user |
| `GET /v1/users/{id}/currency` (economy.roblox.com) | Robux balance |
| `GET /v2/economy-creator-statistics/users/{id}` | Economy stats |

## Shop / purchases

| Endpoint | Método |
|----------|--------|
| `POST /v1/purchases/products/{productId}` | Buy item |
| `GET /v1/game-pass/{id}` | Gamepass info |

## Misc

| Endpoint | Método |
|----------|--------|
| `GET /games/{placeId}` (games.roblox.com) | Place metadata |
| `POST /v1/account/pin/lock` | Lock account PIN |

## CSRF token lifecycle

Cada vez que Rakbot hace un POST, Roblox devuelve 403 la primera vez con header `x-csrf-token: XXXX`. Rakbot captura este header y retries el POST con `x-csrf-token: XXXX` → 200.

Token válido ~10 min, se rota.

## Status codes relevantes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 400 | Bad request (payload malformado) |
| 401 | Cookie inválida / expirada / banned |
| 403 | CSRF requerido, o captcha_lock |
| 408 | Timeout |
| 429 | Rate limited (retry-after header) |
| 500 | Roblox internal error (retry OK) |
| 502/503 | Roblox cloud issue (wait + retry) |

## Headers importantes

### Enviados:
```
User-Agent: Roblox/WinInet
Accept: application/json
Referer: https://www.roblox.com/
Origin: https://www.roblox.com
Cookie: .ROBLOSECURITY=<value>
X-CSRF-TOKEN: <token>              (POSTs only)
Content-Type: application/json     (POSTs only)
```

### Respondidos (detectar estado):
```
rblx-challenge-id      → captcha needed
rblx-challenge-type    → captcha / voice / facial
x-csrf-token           → refresh needed
retry-after            → seconds to wait on 429
Set-Cookie             → ignore, no cookie rotation here
```

## UDP transport (NO HTTP)

Después del join, Roblox negocia UDP con RakNet modificado + ChaCha20-Poly1305. Esto NO va por proxy (DataImpulse HTTP-only).

Puerto destino: variable (lo da el GameJoin response en `IPAddress:Port`).

## Place IDs conocidos

| Game | Place ID |
|------|----------|
| MM2 (Murder Mystery 2) | `142823291` |
| Steal a Brainrot | `109983668079237` |
| Steal An Egg | `107778070777162` |

## Links

- [[01-rakbot-remotes]]
- [[02-mm2-remotes]]
- [[../rakbot-deep-dive/bootstrap-flow]]

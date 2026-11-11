# Troubleshooting — captcha_lock on cookie

## Síntoma

En logs:
```json
{"event": "error", "message": "Roblox requires an additional challenge; complete account sign-in in its official client/site."}
```

O al correr validator:
```
cookies.captcha_lock.txt   3  -> cookies.captcha_lock.txt
```

O respuesta 403 con header `rblx-challenge-id: XXXX`.

## Causa

Roblox marcó la cuenta por:
- Login desde una IP nueva no antes vista
- Cambio brusco de ubicación geográfica (login AR, luego US en 1h)
- Behavioral patterns raros (muchos joins rápidos)
- Random secundary verification trigger

El server exige que un humano resuelva un FunCaptcha en roblox.com antes de aceptar más requests autenticados.

## Fix (manual, por cookie)

### Paso 1 — identificar qué cookie

Si corre validator, está ya en `cookies.captcha_lock.txt`. Formato:
```
captcha_lock   _|WARNING:-DO-NOT-SHARE...<cookie>
```

Mapear esa cookie al username. Opción 1: cada cookie tiene `uid=XXXXX` embebido en el blob, decodeable. Opción 2: validator deja `user_id` al final (si lo detectó antes del lock).

### Paso 2 — abrir en navegador

1. Firefox / Chrome en modo privado
2. Ir a `roblox.com`
3. Abrir DevTools (F12) → tab "Application" / "Storage" → cookies → roblox.com
4. Click "Add cookie" → name = `.ROBLOSECURITY`, value = `<pegar el blob _|WARNING...>`, domain = `.roblox.com`, path = `/`, HttpOnly ☑
5. Refresh la página
6. Debería mostrar el captcha

### Paso 3 — resolver

FunCaptcha es el típico "pick all images with cars" puzzle. 30-60 segundos.

### Paso 4 — verificar

Tras resolver, la cuenta queda logeada. Hacer login navegar unas pags (profile, inventory) → warm-up normal.

### Paso 5 — extract cookie "limpia"

La cookie actual (misma value) ahora funciona para API calls. Copiala de vuelta a `cookies.txt`.

## Fix automático (semi-manual)

Herramientas tipo **2Captcha** o **AntiCaptcha** resuelven FunCaptcha por ti vía API por ~$0.003 por solve. Workflow:

```python
# pseudocode — esto NO está implementado
import twocaptcha

for cookie in open("cookies.captcha_lock.txt"):
    # Load the captcha challenge
    challenge = get_challenge_for_cookie(cookie)
    # Send to 2captcha
    token = twocaptcha.solve(challenge, funcaptcha=True)
    # Submit token back to roblox
    requests.post("https://roblox.com/funcaptcha/submit", 
                  data={"token": token}, 
                  cookies={".ROBLOSECURITY": cookie})
    # Save cookie as "live"
```

**Costo**: $3 por 1000 captcha_locks resueltos. Viable si tenés >50 cookies en captcha_lock.

## Prevención

### 1. Usar siempre la MISMA IP por cookie (sticky proxy)

Nuestra `ProxyPool.url_for(account_id)` ya hace esto. Clave: NO cambiar el `account_id ↔ cookie` mapping entre runs. El actual mapping es `hash(cookie) % len(proxies)`.

Si recreás `proxies.txt` con diferente count → mapping cambia → cuentas salen por IPs nuevas → captcha_lock avalanche.

### 2. Warm-up de cookies nuevas

Antes de usar una cookie en bot:
- Loguear 1 vez via browser desde la IP designada
- Navegar unas páginas (profile, inventory, friends)
- Esto "registra" la IP como conocida para esa cuenta

Costo: 2 min por cookie. Solo relevante si es cookie recién comprada.

### 3. NO forzar logins paralelos

Si corrés N subprocesses en el mismo instant → N requests simultáneos al identity endpoint desde IPs distintas → Roblox detecta "login spam", marca batch.

Fix: `MassRunner.launch` ya tiene throttle entre launches. Verificar que `_next_launch` tenga delay ~1-2s.

### 4. Rate limit awareness

NO hagas >5 auth-like requests por minuto por cookie. Si validator corre con workers=50 → 50 requests paralelos. Si vas a tener 1000+ cookies, usar workers=20 en vez de 100.

## Si tu BATCH ENTERO viene con captcha_lock

Patrón: el proveedor de cookies ya las usó en bots → Roblox las marcó antes de venderlas.

Fix: 
- Pedir refund al proveedor
- Rotar a otro proveedor
- NO usar más esas cookies (ya no tiene value, el daño está hecho)

## Links

- [[00-index]]
- [[../security/00-overview]]
- [[../infrastructure/02-cookies-sources]]

# Infrastructure — fuentes de cookies

## El formato que necesitamos

Solo el valor `.ROBLOSECURITY`:

```
_|WARNING:-DO-NOT-SHARE-THIS...<blob largo>
```

Rakbot acepta con o sin el prefijo `.ROBLOSECURITY=`. Un cookie por línea en `cookies.txt`.

## Mercados

### Bulk cheap ($0.01-0.05/cookie)

| Proveedor | Precio | Calidad | Frescura |
|-----------|--------|---------|----------|
| RoCracked | $0.01 | ~30% live post-valido | semanas-meses |
| NexusGen | $0.03 | ~50% live | días-semanas |
| CookieStock | $0.05 | ~60% live | días |
| ProxyShare | $0.02 | ~20% live | antiguas |

**Estrategia**: compra 3-5× más de las que necesitás vivas. Si querés 500 vivas, pedí 2000.

### Aged (>1 año, más resistentes)

| Proveedor | Precio | Nota |
|-----------|--------|------|
| ClassicRoblox | $1-3/cuenta | Cuentas 2015-2020 |
| VintageAcc | $5/cuenta | Con items de evento viejos |
| OGSellers | $10+ | Aged + algo de inventario |

**Ventaja aged**: Roblox es menos agresivo con cuentas con years_old > 1. Ban masivo golpea primero cuentas <30 días.

### Con inventario (más caras, mejor ROI potencial)

| Proveedor | Precio | Nota |
|-----------|--------|------|
| PlayerAuctions | $0.50-5 | Con Robux + items random |
| RSellers | $1-10 | Verificable, escrow |
| RoCom | $3-8 | Mayormente MM2 inventory |

Si tu meta es Embersickle farming, no necesitás inventario. Pero si vas a hacer trading entre tus propias cuentas (e.g. acumular Godlies en 1 "mother account"), las con inventario arrancan con algo.

### Generadores propios

Si queremos farma nuestras cookies:

- **AutoRoblox** — generador con 2Captcha, ~$0.02/cuenta
- **CookieGen OpenSource** — github.com/.../robloxcookiegen (abandoned)
- **Rakbot propio** — hay que escribir bootstrap que se registre vs el endpoint signup. Complejo.

Problemas con generadores:
- Captcha solver ($0.001 por solve = $1 por 1000 cookies pero slow)
- Email verification requerida (temp mails: `inboxkitten.com`, `tempmail.io`)
- Cuentas <24h son target #1 del anti-cheat masivo

## Workflow de recepción

1. **Compra batch** → recibís archivo `.txt` con cookies
2. **Preview**: abrir en editor, confirmar formato `_|WARNING...`
3. **Copia a `cookies.txt`** en el proyecto
4. **Correr validator**:
   ```bash
   python -m rakbot.validate_cookies --cookies cookies.txt \
       --proxies proxies.txt --workers 50
   ```
5. **Separar por bucket**:
   - `cookies.live.txt` → listas para farm
   - `cookies.captcha_lock.txt` → **manuales**: abrí en navegador, resolvé captcha, movés a `live`
   - `cookies.ban_perm.txt` + `cookies.ban_temp.txt` + `cookies.facelock.txt` + `cookies.2fa.txt` → **descartar**
   - `cookies.ratelimit.txt` → esperar 24h, re-validar

6. **Mover `cookies.live.txt` → `cookies.txt`** para el farm:
   ```bash
   cut -f2 cookies.live.txt > cookies.txt
   ```

7. **Backup del batch original** fuera del repo por si querés auditar después:
   ```bash
   cp cookies.txt backup/cookies-$(date +%Y%m%d).txt
   ```

## Seguridad de cookies

- **NUNCA** las subás a git (verificar `.gitignore` ANTES de `git add`)
- **NUNCA** las mandes por Discord, Telegram, Discord webhook
- **NUNCA** las mostres en pantalla si estás streamando/compartiendo pantalla
- **NUNCA** las uses en navegador sin cuidado — si abrís `inspect element` en roblox.com, te pueden sniffear
- **Si una se filtra**, el owner del leak puede logear como vos y robar inventario en **5 segundos**

## Lifecycle típico de una cookie

```
Día 0 — comprada / generada     cookies.live
Día 1-7 — ok, farmeando         cookies.live
Día 5-15 — primeros captcha     cookies.captcha_lock (manual solve)
Día 10-30 — ban_temp random     cookies.ban_temp (esperar o descartar)
Día 20-45 — ban permanente      cookies.ban_perm (descartar)
Día 30-90 — facelock trigger    cookies.facelock (irreversible, descartar)
```

Tasa de mortalidad típica: **~50% kill en primer mes** si corrés 24/7 con MM2 farm. Reponer stock semanalmente.

## Links

- [[00-overview]]
- [[../mm2-port/00-status]]
- [[../security/01-cookie-safety]]

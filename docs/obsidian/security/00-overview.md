# Security — overview

## Modelo de amenazas

| Amenaza | Impacto | Mitigación en place |
|---------|---------|---------------------|
| `.ROBLOSECURITY` leak | **CRÍTICO** (cuenta robada) | gitignore + env vars + no logs |
| `MM2_DISCORD_WEBHOOK_URL` leak | Medio (spam en canal) | env var + no commit + regenerable |
| `proxies.txt` creds leak | Medio ($ pérdida) | gitignore + password único |
| Roblox detecta patrón | Alto (batch ban) | residential proxies + delays + max N cuentas por IP |
| VPS comprometido | Alto (todas las cookies expuestas) | ssh-key only, ufw, chmod 600 |
| MITM en proxy residential | Alto (cookies en claro) | HTTPS only, DataImpulse auditable |
| Script Python subido a VPS con secret | Alto (git log search) | environment vars solamente |

## Checklist antes de cada commit

```bash
# Verificar que archivos sensibles están ignorados
git check-ignore cookies.txt proxies.txt proxies.local.json cookies.live.txt

# Nunca debería haber output que NO incluya esos archivos
# Si git check-ignore devuelve vacío para alguno → NO COMMITEES hasta arreglar

# Revisar diff a commitear
git diff --cached | grep -iE "(roblox|cookie|password|_|WARNING)" && echo "⚠️ SECRET IN DIFF"

# Si aparece algo con _|WARNING → ABORT
```

## `.gitignore` actual (verificar que tiene todo)

```
cookies.txt
cookies.live.txt
cookies.dead.txt
cookies.ratelimit.txt
cookies.captcha_lock.txt
cookies.captcha_join.txt
cookies.facelock.txt
cookies.2fa.txt
cookies.ban_temp.txt
cookies.ban_perm.txt

proxies.txt
proxies.local.txt
proxies.list
proxies.local.json

scripts/mm2-candy-farm/webhook.local.lua
scripts/mm2-candy-farm/*.local.lua

.env
*.secret
*.cookies
```

Si falta alguno, agregar YA.

## Rotación de secretos

- **Cookies**: cada 30 días, descartar cookies.live viejas y comprar nuevas (incluso las "sanas" acumulan fatiga y marcas)
- **Discord webhook**: regenerar desde Discord si sospechás leak; servidor → canal → integrations → webhooks → delete + create
- **DataImpulse password**: regenerar desde dashboard cada 90 días, actualizar `proxies.txt`
- **SSH keys al VPS**: rotar cada 180 días

## Qué hacer si una cookie se filtra

1. **Inmediato**: logout de la cuenta en Roblox.com → `Settings → Security → Sign out of all sessions`
2. **Esto invalida la cookie actual** → el atacante no puede entrar ya
3. Generar nueva cookie loggeando de vuelta
4. Agregar `2FA` a esa cuenta para prevenir re-robo
5. Investigar cómo filtró (git log, screenshot, Discord, etc.)

## Qué hacer si el VPS se compromete

1. Kill switch: `shutdown -h now` desde cualquier otra terminal
2. Snapshot forense del disco (Hetzner tiene snapshots instantáneos)
3. Logout masivo: para cada cookie en `cookies.txt`, ir a Roblox.com y sign-out
4. Revisar `~/.bash_history`, `/var/log/auth.log`
5. Rebuild desde cero en VPS nuevo

## Detección pasiva

- Monitorear si tus cuentas tienen trades inesperados en inventory
- Monitorear si el total Robux baja sin motivo
- Monitorear si tus cuentas aparecen baneadas en masa el mismo día (patrón de IP block vs individual ban)

## Links

- [[01-cookie-safety]]
- [[02-anti-detection]]
- [[03-mm2-anticheat]]

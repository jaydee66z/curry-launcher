# Security — cookie recovery after leak

> Si una cookie se filtró (o sospechas), este es el procedimiento.

## Signos de que una cookie fue usada por otro

### Checkable via API

```python
# Con la cookie, ver login history
import urllib.request, json
req = urllib.request.Request(
    "https://users.roblox.com/v1/users/authenticated",
    headers={"Cookie": f".ROBLOSECURITY={cookie}",
             "User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    print(json.loads(r.read()))
```

Si funciona → cookie sigue válida. Si 401 → ya fue invalidada (por vos o atacante).

### Checkable via Roblox website

- Login manual a roblox.com con la cuenta
- Settings → Security → **Sign out of all sessions** (recomendado inmediato)
- Settings → Security → "Previous Sessions" (si Roblox muestra) → ver IPs raras

### Checkable via inventory

- Ver si hay items "trades recientes" que vos no hiciste
- Ver si Robux balance bajó sin motivo

## Recovery procedure (si confirmas leak)

### Paso 1 — INVALIDATE la cookie actual

Login Roblox web con la cuenta → Settings → Security → **Sign out of all sessions**.

Esto mata TODAS las sesiones activas (incluye la del atacante y la tuya).

### Paso 2 — Cambiar password

Settings → Account Info → Change Password.

Nueva password fuerte (16+ chars, mixed).

### Paso 3 — Enable 2FA

Settings → Security → 2-Step Verification → Authenticator app (Google Authenticator, Authy).

**Guarda el QR + backup codes en password manager offline**.

### Paso 4 — Generar nueva cookie

Login web con nuevo password → DevTools (F12) → Application → Cookies → copy `.ROBLOSECURITY` value.

### Paso 5 — Reemplazar en `cookies.txt`

```bash
# Find and replace la cookie vieja por la nueva
sed -i "s|OLD_COOKIE_VALUE|NEW_COOKIE_VALUE|g" cookies.txt
```

### Paso 6 — Restart farm para aplicar

```bash
sudo systemctl restart mm2farm
```

## Recovery de inventory (si hay robo)

Si el atacante robó items:
- Ir a `support.roblox.com`
- "I was hacked" form
- Proveer: username, email, approximate date/time of unauthorized access
- Roblox puede rollback trades hechos en últimas 72h si demostrás que no fuiste vos

**Importante**: rollback NO está garantizado. Depende de:
- Si tenés billing history (más probable)
- Si la cuenta tiene inversión real ($ spent on Robux)
- Si Roblox decide (discretion)

## Preventive measures

### 1. Cookie rotation periódica

Cambiar la cookie cada 30-60 días (via Sign out all + re-login + capture new cookie). Reduce ventana de exposición si algún leak futuro.

### 2. 2FA en todas las cuentas valiosas

Para las 1-2 "mother accounts" de agregation:
- OBLIGATORIO 2FA
- Backup codes guardados offline
- No usar SMS (SIM swap risk) — usar app

### 3. Email único por cuenta

NO usar el mismo email para 100 cuentas. Si leak de email → attacker conecta múltiples cuentas.

Idealmente:
- Mother accounts: email real tuyo (recovery seguro)
- Farm accounts: tempmails o aliases (@mail.com + unique)

### 4. No reutilizar passwords

Password manager (Bitwarden, 1Password) con generate unique per cuenta.

### 5. Backup de cookies (encrypted)

Para recovery si borrás el VPS accidentalmente:

```bash
gpg --symmetric --cipher-algo AES256 cookies.txt
# Mover a Dropbox encriptado o pendrive
```

## Post-leak audit

Después del incident, review:

1. **Cómo leakó?**
   - Git commit → check git log all branches
   - Discord screenshot → check channel history
   - VPS compromised → audit auth.log
   - 3rd party service → ?

2. **¿Qué otros secretos tocó?**
   - proxies.txt también? → regenerar DataImpulse password
   - Webhook URL? → regenerar Discord webhook

3. **¿Cómo prevenir?**
   - Gitignore strict + check-ignore antes de cada commit
   - No screenshots con sensitive editors abiertos
   - 2FA en todo

## Si no podés recuperar (cuenta terminada)

Si Roblox declara la cuenta "terminated" por el ataque:
- Los items se pierden
- Robux se pierden
- Account valor → cero

**Mitigación futura**:
- Nunca acumular >$50 de valor en 1 cuenta bot (distribuí)
- Mother accounts con 2FA para los valiosos
- Insurance: no realmente existe para Roblox items

## Legal

Si la cookie fue robada por un contratista o alguien conocido:
- Es "unauthorized computer access" en muchas jurisdicciones (CFAA en US, equivalente en otros)
- Report a Roblox + considerá reporte a autoridades si pérdida es significativa

Si fue un accidente tuyo (tú commiteaste) — asumí pérdida, aprende, mejorá pipeline.

## Links

- [[00-overview]]
- [[01-cookie-safety]]
- [[../deployment/03-incident-response]]

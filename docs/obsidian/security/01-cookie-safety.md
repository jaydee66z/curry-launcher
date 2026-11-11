# Security — cookie safety deep dive

## Qué es realmente `.ROBLOSECURITY`

Es un HTTP cookie de sesión, formato:

```
_|WARNING:-DO-NOT-SHARE-THIS-OR-...<base64 blob>|_<base64 payload>.<signature>
```

El blob base64 contiene:
- `duid` — device UID (random, no identifica realmente)
- `uname` — tu username
- `uid` — tu user_id (el que ves en /users/XXXX)
- otros flags

La `.firma` (parte después del segundo `|_`) es una HMAC del server. Sin ella, no sirve.

**La cookie NO contiene tu password.** Si la cambiás después, la cookie sigue funcionando hasta que hagas `Sign out of all sessions`.

## Lifecycle de una sesión

| Evento | Qué pasa con la cookie |
|--------|------------------------|
| Login con password | Server genera cookie, SSH la pone en Set-Cookie header |
| Logout (click normal) | Cookie se borra del navegador, pero el token sigue válido en server |
| **Sign out of all sessions** | Server invalida el token → cookie muere |
| Change password | Cookie sobrevive (!!) — solo "sign out all" la mata |
| 30 días sin uso | Roblox a veces expira automáticamente |
| Account suspended | Server devuelve 401, cookie útil pero inútil |

## Attack vectors reales

### 1. Git commit accidental

Peor pesadilla. Alguien pushea `cookies.txt` → GitHub escanea → cookies quedan en search index de hackers.

**Mitigación**: 
- `cookies.txt` en `.gitignore` ANTES de crear el archivo
- `git check-ignore` siempre antes de `git add -A`
- Nunca usar `git add .` o `git add -A` — siempre explícito

### 2. Log dumps

Si imprimo `print(credential.value)` por debug → aparece en logs → VPS log search → leak.

**Mitigación**:
- `Credential.__repr__` ya devuelve `"<redacted>"` (ver `bootstrap.py:148`)
- Nunca hagas `str(credential)` en código
- Nunca pases la cookie a Discord webhook, email, Slack, etc.

### 3. Discord screenshots

Si estás streameando o compartiendo pantalla para pedir ayuda, y tu editor tiene cookies.txt abierto → leak visible.

**Mitigación**:
- Cerrar editor de cookies antes de screenshot
- No abrir `cookies.txt` en VSCode sincronizado con settings sync

### 4. VPS compromise

SSH brute force → acceso root → cat cookies.txt → game over.

**Mitigación**:
- Deshabilitá `PasswordAuthentication` en sshd, solo key auth
- `ufw allow ssh`, deny everything else inbound
- `fail2ban` auto-ban IPs que intentan brute force
- Permisos 600 en cookies.txt (`chmod 600`)

### 5. MITM en proxy

El dueño del proxy puede ver tu tráfico. Si Roblox API fuera HTTP, verían la cookie en claro.

**Mitigación**:
- **Roblox API es HTTPS only** → TLS encripta la cookie
- Proxies SOCKS5 no pueden decrypt TLS sin certificate injection
- DataImpulse tiene reputation OK — pero igual, prefiere HTTPS everywhere

### 6. Browser Extension malware

Si abrís la cuenta en Chrome con una extensión maliciosa instalada → la ext lee todas tus cookies de roblox.com.

**Mitigación**:
- Usar un browser dedicado solo para Roblox (sin extensions)
- O usar modo Incognito siempre

### 7. Phishing al proveedor de cookies

Si comprás cookies en RoCracked, el vendor también tiene tus cookies. Si ellos las venden a 20 clientes diferentes → tus cuentas se banean en lote.

**Mitigación**:
- Rotar proveedor de vez en cuando
- Usar cookies por tiempo limitado (semanas, no meses)
- Nunca mezclar cookies "valiosas" (cuentas tuyas de verdad) con bulk compradas

## Qué información se puede extraer de una cookie

1. **UserId**: hacé `GET /v1/users/authenticated` con la cookie → devuelve `{id, name, displayName}`
2. **Robux balance**: `GET /v1/users/CURRENTLY_LOGGED_IN/currency`
3. **Inventory**: `GET /v1/users/USER_ID/inventory/...`
4. **Email**: `GET /v1/account/settings/email`
5. **Phone**: `GET /v1/account/settings/phone`

Con eso, el atacante puede:
- Vender tu inventario a sus propias cuentas (trade)
- Comprar items con tus Robux
- Marcar la cuenta para phishing targeted
- Contactar soporte Roblox "I lost my account" (si tiene email+phone)

## Signos de que una cookie fue usada por otro

- Trades inesperados en inventory
- Robux bajó sin motivo
- Items transferidos a cuentas que no reconocés
- Login history muestra IPs en otros países (`https://www.roblox.com/my/account#!/privacy`)

## Backup de cookies — cómo hacerlo seguro

Si querés guardar una copia por si Falla el disk del VPS:

```bash
# Cifrar con GPG antes de mover a cloud
gpg --symmetric --cipher-algo AES256 cookies.txt
# Produce cookies.txt.gpg, puede subirse a Dropbox/GDrive seguro

# Para recuperar:
gpg --decrypt cookies.txt.gpg > cookies.txt
```

**NO usar** `base64` o `zip` solos — eso no es cifrado, solo encoding.

## Links

- [[00-overview]]
- [[../infrastructure/02-cookies-sources]]

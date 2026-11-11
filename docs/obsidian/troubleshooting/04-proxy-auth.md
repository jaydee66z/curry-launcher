# Troubleshooting — proxy auth failures

## Síntoma

```json
{"event": "transport_err", "stage": "auth", "err": "HTTP 407 Proxy Authentication Required"}
```

o

```python
urllib.error.HTTPError: HTTP Error 407: Proxy Authentication Required
```

## Causa

Credenciales DataImpulse en `proxies.txt` no coinciden con las del panel.

## Fix

### Paso 1 — verificar formato del archivo

```bash
head -3 proxies.txt
```

Esperado:
```
USER__cr.us,ca:PASS@gw.dataimpulse.com:10000
USER__cr.us,ca:PASS@gw.dataimpulse.com:10001
...
```

Verificaciones:
- [ ] `USER` es el username del dashboard
- [ ] `PASS` es el password del dashboard (SIN quotes)
- [ ] `@` separa credenciales de host
- [ ] `gw.dataimpulse.com:10000+N` — endpoint + port correcto

### Paso 2 — test manual con curl

```bash
# Elegí una línea cualquiera, e.g. la línea 1:
PROXY=$(head -1 proxies.txt)
curl -x "http://$PROXY" https://api.ipify.org
```

Esperado: devuelve una IP (no la del VPS, una residencial).

Si devuelve `407`:
- Revisar user/pass copiadas exact del dashboard
- Verificar que tu plan DataImpulse esté activo (saldo >0)
- Puede que DataImpulse requiera "username normal" sin `__cr.XX` prefix — revisar panel

### Paso 3 — verificar que el país es válido

El formato `__cr.us,ca,de,fr,mx,gb` dice "cualquiera de US, CA, DE, FR, MX, GB". Si pedís `__cr.xx` que no está en tu plan → 407.

Fix: ajustar a solo países disponibles:

```bash
# Si tu plan solo tiene US/CA/DE:
sed -i 's/__cr\.[a-z,]*:/__cr.us,ca,de:/g' proxies.txt
```

### Paso 4 — DataImpulse account issues

Posibilidades:
- **Plan expirado**: dashboard muestra "0 GB restantes" → recargar
- **Password changed** por otro usuario: revisar notifications panel
- **Account suspended** por abuse → contactar support

## Prevención

- **No regenerar password frecuentemente** — cada regeneración requiere update del `proxies.txt`
- **Backup del archivo** encrypted:
  ```bash
  gpg --symmetric --cipher-algo AES256 proxies.txt
  # Guarda proxies.txt.gpg off-site (Dropbox encrypted, etc)
  ```
- **Alert si quota < 10%**: setup un cron que ping DataImpulse API y mande alert Discord

## Fallback: direct connection

Si DataImpulse está down pero tenés que correr URGENTE:

```bash
# Elimina proxies.txt temporariamente
mv proxies.txt proxies.txt.bak

# Rakbot detecta ausencia → ProxyPool.enabled() = False → direct connect
python -m rakbot mass --mm2 --mass-cookies 5 ...
```

⚠️ Esto saca TODAS las cuentas desde tu IP. Para <5 cuentas corre ratos. **NO** usar >10 cuentas direct o te quemás tu IP.

## Links

- [[00-index]]
- [[../infrastructure/01-proxies-dataimpulse]]

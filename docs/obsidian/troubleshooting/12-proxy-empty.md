# Troubleshooting — `ProxyPool.enabled() == False`

## Síntoma

Al construir pool:
```python
from rakbot.proxy_pool import ProxyPool
p = ProxyPool()
print(p.enabled())   # False
print(p.count())     # 0
```

O en logs del subprocess:
```json
{"event": "authenticated", "user_id": ..., "proxy_pool": false}
```

Esperábamos `proxy_pool: true`.

## Causa 1 — `proxies.txt` no existe

```bash
ls -la proxies.txt
```

Si "No such file or directory" → el archivo nunca fue creado o se borró.

Fix: crear o restaurar from backup:
```bash
# Si tenés backup encrypted
gpg --decrypt proxies.txt.gpg > proxies.txt
```

## Causa 2 — `proxies.txt` está vacío o solo comentarios

```bash
grep -v '^#' proxies.txt | grep -v '^$' | wc -l
```

Si devuelve `0` → no hay líneas de proxy, solo header de comentarios.

Fix: pegar las 2000 líneas DataImpulse.

## Causa 3 — path wrong

`ProxyPool()` busca en orden:
1. `proxies.txt` (en current working directory)
2. `proxies.local.txt`
3. `proxies.list`

Si corrés desde un directorio distinto a `curry-launcher/`, no encuentra.

Verificar:
```python
import os
print(os.getcwd())
```

Si `/root/` o `/home/user/` en vez de `/home/user/curry-launcher/` → change to right dir:
```bash
cd ~/curry-launcher
python -m rakbot mass ...
```

O pasar path explícito en código:
```python
pool = ProxyPool("/home/farmbot/curry-launcher/proxies.txt")
```

## Causa 4 — todas las líneas malformadas

Si cada línea de `proxies.txt` es basura (sin `@`, sin `:port`):
```
# Bad:
https://gw.dataimpulse.com
gw.dataimpulse.com
10000
```

El parser `_parse_line` las skippea → count=0.

Fix: formato correcto. Ver [[../infrastructure/01-proxies-dataimpulse]] para template.

## Causa 5 — permisos de lectura

Si `proxies.txt` tiene permisos `000` o root-only:
```bash
ls -la proxies.txt
# -rw------- root root ...   ← solo root puede leer, pero vos corres como farmbot
```

Fix:
```bash
sudo chown farmbot:farmbot proxies.txt
sudo chmod 600 proxies.txt
```

## Diagnóstico profundo

Instrumentar `_parse_line` temporal:
```python
# rakbot/proxy_pool.py
def _parse_line(raw: str) -> Optional[str]:
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    result = ...  # original logic
    if result is None:
        import sys
        print(f"[proxy_pool] FAILED to parse: {line[:60]}", file=sys.stderr)
    return result
```

Correr una vez:
```python
from rakbot.proxy_pool import ProxyPool
p = ProxyPool("proxies.txt")
# verás stderr con cada línea rejected
```

Ajusta el formato según lo que diga.

## Causa 6 — Windows line endings

Si `proxies.txt` fue creado en Windows y copiado via FTP binario a Linux VPS, puede tener `\r\n` que el parser trat como parte del password.

Fix:
```bash
dos2unix proxies.txt
```

O reemplazar manualmente:
```bash
sed -i 's/\r$//' proxies.txt
```

## Verificación final

Después de fix:
```python
from rakbot.proxy_pool import ProxyPool
p = ProxyPool()
print(f"enabled: {p.enabled()}, count: {p.count()}")
print(f"account 0: {p.url_for(0)[:40]}...")
```

Esperado:
```
enabled: True, count: 2000
account 0: http://USER__cr.XX:PASS@gw.dataimpulse.c...
```

## Links

- [[00-index]]
- [[../infrastructure/01-proxies-dataimpulse]]

# Infrastructure — DataImpulse proxy pool

## Setup actual

Formato de archivo: `proxies.txt` (gitignored). Una línea por slot sticky:

```
USERNAME__cr.<countries>:PASSWORD@gw.dataimpulse.com:10000
USERNAME__cr.<countries>:PASSWORD@gw.dataimpulse.com:10001
...
USERNAME__cr.<countries>:PASSWORD@gw.dataimpulse.com:11999
```

Cada puerto `10000+N` = 1 IP residencial sticky pinned a esa sesión.

En `rakbot/proxy_pool.py`:
```python
ProxyPool.url_for(account_id) = lines[account_id % len(lines)]
```

El account_id proviene del index de la cookie en `cookies.txt` (0, 1, 2, ...). Mapping **estable**: la misma cuenta siempre sale por la misma IP, incluso después de restart.

## Países configurados

`__cr.sg,ca,de,fr,mx,gb,us` significa que DataImpulse puede elegir salida en:
- Singapore
- Canada
- Germany
- France
- Mexico
- United Kingdom (`gb`)
- United States

Agregá `ar` (Argentina), `do` (RD) si están en tu plan. Codes ISO 3166-1 alpha-2 en minúscula.

## Métricas esperadas

| Métrica | Valor |
|---------|-------|
| IPs únicas disponibles | ~40k (`United States (40990 IPs)` según dashboard) |
| Latencia típica | 150-250ms |
| Uptime por slot | 99%+ |
| Rotación en sticky | Cada 10 min (según panel) |
| Protocolo | HTTP/HTTPS (CONNECT tunnelling) |
| Autenticación | Basic auth en URL |

## Consumo real (por cuenta Roblox)

Solo el tráfico HTTP(S) a Roblox API pasa por el proxy. El tráfico UDP de game NO (DataImpulse no soporta UDP, pasa direct).

| Actividad | Datos/hora |
|-----------|-----------|
| Auth inicial (1 vez) | ~200 KB |
| Join game (cada ronda) | ~500 KB |
| ProfileData polling (1/min) | ~50 KB/hora acumulado |
| Inventory updates | ~100 KB/hora |
| **Total por cuenta activa** | **~3-5 MB/hora** |

Para 1000 cuentas activas 1 hora → **3-5 GB consumidos**.

## Cálculo de plan

| Cuentas activas 24/7 | GB/mes | Costo @ $1/GB |
|---------------------|--------|---------------|
| 10 | ~1 GB | $1 |
| 50 | ~5 GB | $5 |
| 100 | ~10 GB | $10 |
| 500 | ~50 GB | $50 |
| 1000 | ~100 GB | $100 |

## Cómo verificar en vivo

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -c "
from rakbot.proxy_pool import ProxyPool
import urllib.request

p = ProxyPool('proxies.txt')
print(f'pool enabled: {p.enabled()}, slots: {p.count()}')

for aid in (0, 100, 500, 1000, 1999):
    url = p.url_for(aid)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({'http': url, 'https': url}))
    try:
        r = opener.open('https://api.ipify.org?format=json', timeout=15)
        print(f'account {aid}: {r.read().decode()}')
    except Exception as e:
        print(f'account {aid}: ERR {e}')
"
```

Resultado esperado:
```
pool enabled: True, slots: 2000
account 0: {"ip":"23.45.67.89"}
account 100: {"ip":"185.23.45.67"}
account 500: {"ip":"78.91.123.45"}
account 1000: {"ip":"192.168.X.Y"}
account 1999: {"ip":"201.25.45.67"}
```

Cada account_id → IP diferente → **pool working**.

## Errores comunes

| Error | Causa | Fix |
|-------|-------|-----|
| `407 Proxy Authentication Required` | Credenciales mal | revisar user/pass en `proxies.txt` |
| `502 Bad Gateway` | Slot caído temporalmente | retry; sticky session tarda 10s a veces |
| `407 Country not available` | País no incluido en plan | revisar DataImpulse dashboard |
| Timeout 15s+ | DataImpulse overloaded | fallback a slot vecino manual |
| Roblox 403 constante por una IP | IP marcada por Roblox | rotar — `account_id → siguiente slot` |

## Rotación manual si un slot se quema

Manualmente excluir una línea:

```bash
# Encuentra el line number
grep -n "10050" proxies.txt
# Comentalo con #
sed -i 's|^\(USER.*:10050.*\)|# BURNED \1|' proxies.txt
```

El mapping se ajusta automáticamente porque `account_id % len(active_lines)` cuenta solo las líneas no-comentadas.

## Links

- [[00-overview]]
- [[02-cookies-sources]]
- [[../mm2-port/01-architecture]]

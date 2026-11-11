# Troubleshooting — DataImpulse quota explosion

## Síntoma

En DataImpulse dashboard: consumo salta de "normal" a 2-5x el día previo. 10 GB/día → 50 GB/día.

Al mes: $500+ gastados en 1 semana.

## Causas

### 1. Game UDP traffic leakeó por proxy

El ChaCha-encripted UDP de MM2 es ~160 Mbps por cuenta cuando está activa. **No debería** pasar por proxy (DataImpulse es HTTP-only).

Si por algún bug Rakbot routea UDP:
- 160 Mbps × 10 cuentas × 1 hora = 72 GB/hora
- Un día: 1.7 TB — way over cualquier plan razonable

**Fix**: Rakbot `persistent_client.py` usa UDP sockets directo. NO deberían tocar proxy. Verificar:

```python
# En persistent_client.py o native_client.py:
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# NO debería envolver con proxy
```

Si accidentalmente wrappear con proxy → removelo.

### 2. HTTPS repoll excesivo

Rakbot normalmente hace 1 auth + 1 join inicial + heartbeats keepalive UDP. HTTPS calls adicionales:
- ProfileData polling via HTTPS (si no se puede leer del replicated world)
- Inventory check (si fallback a HTTP)
- Presence pings

Si alguna de estas corre 1/sec por cuenta → 60/min × 1000 cuentas = **60k requests/min a Roblox**. Cada request ~5 KB con headers → 300 MB/min = **18 GB/hora**.

**Fix**: audit intervals:
- ProfileData poll: 60s mínimo
- Presence pings: 300s mínimo
- Inventory refresh: 600s mínimo

### 3. Retry storm

Si Roblox devuelve 429 (rate limit), Rakbot retry. Si retry agressive sin backoff → infinite loop + bandwidth.

**Fix**: exponential backoff en bootstrap:
```python
delay = min(300, 2 ** attempts)  # 1s, 2, 4, 8, ..., max 5 min
time.sleep(delay + random.uniform(0, 1))
```

### 4. Dashboard polling excessive

Si tu web dashboard (ver [[../advanced/02-dashboard-web]]) polls `/stats` cada 500ms → ok para 1 user. Pero si tenés 5 dashboards abiertas en 5 browsers → 10 requests/sec a dashboard → dashboard reads 1 MB logs each → **36 MB/min** = 52 GB/día.

Esto NO pasa por DataImpulse (dashboard es local HTTP), pero si está en VPS público y alguien lo descubrió, lo polls bruto → bandwidth explosion.

**Fix**: auth en dashboard + rate limit a 1 request/user/sec.

### 5. Coincidencia: otro usuario usando tu quota

DataImpulse account compartido → otro usuario usa tus GB sin que sepas.

**Fix**: cambiar password DataImpulse inmediatamente. Enable 2FA si existe.

## Recovery emergency

Si ves la explosion en vivo:

```bash
# PAUSAR TODO
sudo systemctl stop mm2farm

# Verificar que no hay otros procesos usando proxy
sudo netstat -tnp | grep dataimpulse

# Si hay → kill
sudo pkill -f dataimpulse
```

Después: investigar con calma. No restart hasta encontrar root cause.

## Prevención

### Quota alerts

DataImpulse tiene alerts automáticos a 50%, 80%, 95%. **Enable las 3**.

### Rate limit en el bot

Cap manual en Rakbot:

```python
# proxy_pool.py — agregar daily cap
class ProxyPool:
    DAILY_GB_LIMIT = 10  # abort si exceedes

    def url_for(self, account_id):
        if self._gb_used_today() > self.DAILY_GB_LIMIT:
            raise RuntimeError("DataImpulse daily cap reached — aborting")
        # ... normal logic
```

Esto es paranoid pero previene explosion.

### Monitoreo cron

```bash
#!/bin/bash
# di_quota_check.sh — cron cada hora
RESPONSE=$(curl -s -u "$DI_USER:$DI_PASS" "https://api.dataimpulse.com/usage")
USED_GB=$(echo $RESPONSE | jq .traffic_used_gb)
PLAN_GB=$(echo $RESPONSE | jq .plan_gb)
PCT=$(echo "scale=0; $USED_GB * 100 / $PLAN_GB" | bc)
if [ $PCT -gt 80 ]; then
  curl -X POST "$MM2_DISCORD_WEBHOOK_URL" -H "Content-Type: application/json" \
    -d "{\"content\":\"⚠️ DataImpulse: ${USED_GB}/${PLAN_GB} GB (${PCT}%)\"}"
fi
if [ $PCT -gt 95 ]; then
  # PAUSAR BOT AUTOMÁTICAMENTE
  sudo systemctl stop mm2farm
fi
```

## Post-mortem después de explosion

```markdown
# Incident YYYY-MM-DD DataImpulse explosion

## Impact
- Gastamos $X en Y días
- Overage sobre plan: Z GB

## Timeline
...

## Root cause
<cuál de las 5 causas>

## Prevention
<fix implementado>
```

## Links

- [[00-index]]
- [[../infrastructure/01-proxies-dataimpulse]]
- [[../infrastructure/05-cost-tracking]]

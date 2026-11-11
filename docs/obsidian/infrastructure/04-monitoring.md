# Infrastructure — monitoreo

## Qué querés saber en vivo

1. **Cuántos subprocesses corriendo** vs objetivo
2. **Pickups/hora total** y **boxes abiertas/hora**
3. **Embersickle drops acumulados** + por qué cuenta
4. **Cookies banned** detectadas durante operación
5. **Rebuilds de heartbeat** (señal de problemas latentes)
6. **GB proxy consumidos** (contra límite plan)

## Dashboard simple con grep + awk (MVP sin programar)

```bash
#!/bin/bash
# save as ~/curry-launcher/dashboard.sh

LOG=~/curry-launcher/logs/mm2farm.log
NOW=$(date +%s)
LAST_HOUR=$((NOW - 3600))

echo "=== MM2 Farm status $(date) ==="
echo
echo "Running subprocesses:    $(pgrep -c mass_worker)"
echo "Pickups last hour:       $(grep -c '\"pickup\"' <(tail -100000 $LOG))"
echo "Boxes opened last hour:  $(grep -c 'box_fired' <(tail -100000 $LOG))"
echo "Embersickle drops total: $(grep -c 'rare_drop' $LOG)"
echo "Rate limits hit:         $(grep -c 'ratelimit' $LOG)"
echo "Rebuilds total:          $(grep -c 'hb_rebuild' $LOG)"
echo "Errors last hour:        $(grep -c '\"error\"' <(tail -100000 $LOG))"
echo
echo "=== Last rare drops ==="
grep 'rare_drop' $LOG | tail -5
```

Ejecutar cada 30 min via cron:
```
*/30 * * * * /home/farmbot/curry-launcher/dashboard.sh | mail -s "MM2 status" tu@email.com
```

## Dashboard web (upgrade)

Idea básica: un `rakbot/dashboard.py` HTTP server que:
1. Lee logs
2. Expone JSON en `/stats`
3. Sirve HTML en `/` con chart.js para los últimos 24h

Estructura sugerida:

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, re
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta

LOG = Path("logs/mm2farm.log")

def parse_last_24h():
    stats = defaultdict(int)
    drops = []
    with LOG.open() as f:
        for line in f:
            try: data = json.loads(line)
            except: continue
            ev = data.get("event", "")
            stats[ev] += 1
            if ev == "rare_drop":
                drops.append(data)
    return {"counts": dict(stats), "drops": drops[-20:]}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(parse_last_24h()).encode())
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())

HTML = """<!DOCTYPE html><html><body>
<h1>MM2 Farm</h1>
<pre id=stats>loading...</pre>
<script>
fetch('/stats').then(r=>r.json()).then(j=>{
  document.getElementById('stats').textContent = JSON.stringify(j, null, 2);
});
setInterval(()=>location.reload(), 10000);
</script></body></html>"""

HTTPServer(("0.0.0.0", 8080), H).serve_forever()
```

Correrlo: `python dashboard.py` → navegá a `http://TU_VPS_IP:8080`.

## Alertas críticas (Discord webhook)

Cuando pasa algo urgente, otro embed:

```python
# Trigger: >10% de cuentas offline
def alert_dead_accounts(count, total):
    if count / total > 0.10:
        send_discord({
            "title": "🚨 ACCOUNT DIE-OFF",
            "description": f"{count}/{total} cuentas caídas (>{int(100*count/total)}%)",
            "color": 15548997,  # red
        })

# Trigger: Embersickle drop (ya implementado en EmbersickleWatcher)

# Trigger: Proxy pool bandwidth > 80%
def alert_proxy_quota(gb_used, gb_cap):
    if gb_used / gb_cap > 0.80:
        send_discord({
            "title": "⚠️ PROXY QUOTA",
            "description": f"DataImpulse: {gb_used}/{gb_cap} GB usados (>{int(100*gb_used/gb_cap)}%)",
            "color": 16776960,  # yellow
        })
```

## Health check endpoints a monitorear

Desde un servicio externo (UptimeRobot, Statuscake):

- `GET http://TU_VPS/stats` → esperar JSON con `counts.pickup > 0` en últimos 10min
- `GET http://TU_VPS/health` → simple 200 OK si process alive

Si cualquiera falla → enviar email alert.

## Logs de DataImpulse

Dashboard en `https://app.dataimpulse.com/`:
- **Usage this period** → GB consumidos vs plan
- **Live sessions** → cuántas IPs activas
- **Errors** → 401/403/countries unavailable

Ideal: check diario.

## Logs de Discord webhook

En Discord server, canal del webhook:
- Embersickle drops (gold/orange embeds)
- Rebuilds/kicks (yellow embeds)
- Alerts críticas (red embeds)

Si no ves webhooks en 1 hora → bot caído o webhook URL broken.

## Kill switch remoto

Si todo explota y no estás cerca del VPS:

```bash
ssh farmbot@TU_IP "sudo systemctl stop mm2farm"
```

o un endpoint de kill en el dashboard:

```python
elif self.path == "/kill":
    import subprocess; subprocess.run(["systemctl", "stop", "mm2farm"])
    self.send_response(200); self.end_headers()
    self.wfile.write(b"stopped")
```

⚠️ **nunca expongas `/kill` sin autenticación** — cualquiera puede apagar tu bot.

## Links

- [[00-overview]]
- [[03-vps-setup]]
- [[../mm2-port/00-status]]

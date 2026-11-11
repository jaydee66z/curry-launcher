# Advanced — web dashboard

> Blueprint para un dashboard web que muestra live stats del farm.

## Why

Monitorear 1000 cuentas via `grep` del log es painful. Web dashboard permite:
- Live counts de pickups, boxes, drops
- Gráficos de trends (24h, 7d)
- Lista de drops recientes con account name
- Status por cuenta (alive, dead, rebuilding)
- Alerts críticas visibles de inmediato

## Stack recomendado

**Minimal**: Python `http.server` + static HTML + chart.js (zero deps extra).

**Medium**: FastAPI + Jinja2 + HTMX (reactive sin JS frameworks).

**Full**: FastAPI + React + Postgres + WebSockets (overkill para 1 persona).

**Recomendado**: MINIMAL por simplicidad.

## Diseño MVP

```
┌──────────────────────────────────────────────────────┐
│  MM2 Farm Dashboard — 2026-11-11 15:23               │
├──────────────────────────────────────────────────────┤
│  Running: 127 bots   |   Dead: 5   |   Rebuilding: 2│
│  ─────────────────────────────────────────────────── │
│  Last 24h:                                           │
│    Pickups:    45,230                                │
│    Boxes:         75                                 │
│    Drops common: 3                                   │
│    Drops chroma: 0                                   │
│                                                      │
│  Revenue est (2026-11 prices):                       │
│    Common 3 × $7 = $21                               │
│    Total est: $21                                    │
│                                                      │
│  ─────────────────────────────────────────────────── │
│  Recent drops:                                       │
│    2026-11-11 14:52  common  Tormenta_2336 (123456)  │
│    2026-11-11 13:28  common  OTAKU172892 (7890)      │
│    2026-11-11 09:14  common  zapicchiwotb2 (54844)   │
│  ─────────────────────────────────────────────────── │
│  [chart: pickups/hour last 24h]                      │
└──────────────────────────────────────────────────────┘
```

## Implementación MVP

```python
# rakbot/dashboard.py  (~150 líneas)
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timedelta

LOG = Path("logs/mm2farm.log")

def parse_logs():
    stats = defaultdict(int)
    recent_drops = deque(maxlen=20)
    with LOG.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except:
                continue
            ev = d.get('event', '')
            stats[ev] += 1
            if ev == 'rare_drop':
                recent_drops.append(d)
    return {
        'running': stats.get('authenticated', 0),  # rough proxy
        'pickups': stats.get('pickup', 0),
        'boxes': stats.get('box_fired', 0),
        'drops_common': sum(1 for d in recent_drops if d.get('variant') == 'common'),
        'drops_chroma': sum(1 for d in recent_drops if d.get('variant') == 'chroma'),
        'recent_drops': list(recent_drops),
    }

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stats':
            data = parse_logs()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        else:
            self.send_response(404); self.end_headers()
    
    def log_message(self, format, *args):
        pass  # quiet

HTML = """<!DOCTYPE html>
<html><head><title>MM2 Farm</title>
<style>
  body { font-family: monospace; background: #111; color: #eee; padding: 20px; }
  .card { background: #222; padding: 15px; margin: 10px 0; border-radius: 4px; }
  h1 { color: #0f0; }
  .big { font-size: 32px; color: #0ff; }
  .drop { padding: 4px 0; border-bottom: 1px solid #333; }
  .common { color: #ff9900; }
  .chroma { color: #ffd700; }
</style></head>
<body>
<h1>MM2 Farm Dashboard</h1>
<div class=card><div class=big id=pickups>…</div> pickups total</div>
<div class=card><div class=big id=boxes>…</div> boxes opened</div>
<div class=card><div class=big id=drops_common>…</div> common Embersickles</div>
<div class=card><div class=big id=drops_chroma>…</div> chroma Embersickles</div>
<div class=card>
  <h3>Recent drops</h3>
  <div id=drops>loading...</div>
</div>
<script>
async function update() {
  const r = await fetch('/stats'); const d = await r.json();
  document.getElementById('pickups').textContent = d.pickups.toLocaleString();
  document.getElementById('boxes').textContent = d.boxes.toLocaleString();
  document.getElementById('drops_common').textContent = d.drops_common;
  document.getElementById('drops_chroma').textContent = d.drops_chroma;
  document.getElementById('drops').innerHTML = d.recent_drops.map(dr =>
    `<div class=drop><span class='${dr.variant}'>${dr.variant.toUpperCase()}</span> ${dr.item || 'Embersickle'} </div>`
  ).join('');
}
update(); setInterval(update, 5000);
</script>
</body></html>"""

if __name__ == '__main__':
    print("Dashboard on http://0.0.0.0:8080")
    HTTPServer(('0.0.0.0', 8080), H).serve_forever()
```

## Deployment en VPS

```bash
# nohup para que siga corriendo al disconnect
nohup python3 rakbot/dashboard.py > dashboard.log 2>&1 &
disown
```

Acceder: `http://TU_VPS_IP:8080`.

Firewall:
```bash
sudo ufw allow 8080
```

## Seguridad

⚠️ **NO exponer sin auth**. Dashboard expone info del farm (número de cuentas, revenue). Si alguien random encuentra el IP:8080 → ventaja competitiva.

Fix: basic auth con nginx reverse proxy:

```nginx
# /etc/nginx/sites-available/dashboard
server {
    listen 443 ssl;
    server_name dashboard.midominio.com;
    auth_basic "Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
# Enter password
sudo systemctl reload nginx
```

## Upgrades futuros

- WebSocket para update sin polling (3x más eficiente)
- Chart.js para gráficos time-series
- Alert trigger si pickups cae a 0 por N minutos
- Export CSV para análisis en Excel
- Multi-VPS aggregation (si tenés 2+ VPS)

## Links

- [[00-server-flooding]]
- [[../infrastructure/04-monitoring]]

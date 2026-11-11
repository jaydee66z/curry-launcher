# Troubleshooting — subprocess crash loop

## Síntoma

En `logs/mm2farm.log`:
```json
{"event": "starting", ...}
{"event": "error", "message": "Worker initialization failed."}
{"event": "starting", ...}  ← rearranca
{"event": "error", ...}
...
```

O un subprocess muere y `MassRunner` lo relanza inmediatamente → loop.

## Causa

Excepción no cacheada en `mass_worker.run()`. Culpables típicos:

1. Cookie malformada → `BootstrapError` → raise → exit
2. Proxy down → `NetworkUnavailable` → raise
3. Python bug en código nuevo → `AttributeError` / `TypeError`
4. `game_client` fail de handshake → `CryptoError`

## Diagnóstico

### Paso 1 — ver el stderr real

Por default, `MassRunner.launch` suprime stderr del subprocess (`stderr=subprocess.DEVNULL`). Bug — hay que verlo:

```python
# TEMPORAL — en mass.py MassRunner.launch, cambiar:
stderr=subprocess.DEVNULL
# A:
stderr=subprocess.PIPE
```

Y en `_reader` (o thread aparte), leer stderr y emitir:

```python
def _stderr_reader(self, session):
    for line in iter(session.process.stderr.readline, b''):
        self.emit(f'account[{session.index}] STDERR: {line.decode(errors="replace").strip()}')
```

Ahora cada crash te dice **exactamente** qué excepción saltó.

### Paso 2 — correr worker standalone con stderr visible

Bypassear mass runner:

```bash
cd ~/curry-launcher
source .venv/bin/activate
echo '{"cookie": "LA_COOKIE_QUE_CRASHEA"}' | \
    python -m rakbot.mass_worker --mm2 --place-id 142823291 --duration 60 2>&1
```

Verás el stack trace directo en terminal.

### Paso 3 — identificar patrón

¿**Todos** los workers crashean o solo algunos?

- Si **todos**: bug Python global (import, syntax, config)
- Si **algunos**: problema específico a esa cuenta (cookie malformada, captcha_lock, proxy slot roto)

```bash
# Contar errores por subprocess
grep 'account\[' logs/mm2farm.log | grep 'error\|STDERR' | awk -F'[\\[\\]]' '{print $2}' | sort | uniq -c | sort -rn | head
```

Si ves `10 account[3]` pero 0 en otros → cuenta 3 tiene problema.

## Fixes comunes

### Fix 1 — cookie malformada

```bash
# En cookies.txt línea N tiene caracteres raros
python3 -c "
with open('cookies.txt') as f:
    for i, l in enumerate(f):
        l = l.strip()
        if l and not l.startswith('#'):
            if any(ord(c) < 33 or ord(c) > 126 or c in ';,\"\\\\' for c in l):
                print(f'Line {i+1} INVALID: {l[:40]}...')
"
```

Eliminar o fix esas líneas.

### Fix 2 — proxy slot down

Si account_id=3 siempre crashea con proxy error:

```python
# Verificar qué slot tiene
from rakbot.proxy_pool import ProxyPool
p = ProxyPool()
print(p.url_for(3))
```

Test ese proxy manualmente:
```bash
curl -x "<URL>" https://api.ipify.org
```

Si 407 → credenciales mal. Si timeout → slot caído.

Fix: comment esa línea en `proxies.txt`:
```bash
sed -i "4s/^/#DEAD /" proxies.txt  # línea 4 (account_id=3) comentada
```

### Fix 3 — Python exception en nuestro código

Dejar el stack trace visible en `logs/mm2farm.log`. Buscar línea del tipo:

```
File "/.../rakbot/mm2_client.py", line 123, in tick
  pos = self.inspector.nodes[XXX]
KeyError: ...
```

Fix depending on root cause.

### Fix 4 — CryptoError de ChaCha

Usualmente: cliente no pudo completar handshake con servidor. Causas:
- Server-side version actualizada incompatible con native 0.744
- Red cortó mid-handshake
- Session ticket inválido

Retry: mass.py ya tiene reintentos — si falla 3 veces consecutivas, cuenta se marca "dead" temporalmente.

### Fix 5 — OOM silencioso

Si subprocess crashea con `Killed` (sin exception), es OOM:
```bash
dmesg | grep -i "killed process"
```

Fix: bajar `max_nodes` del Inspector, reducir cuentas concurrentes.

## Prevención

### 1. Más logging en subprocess

Agregar al principio de `mass_worker.run`:

```python
import traceback
import sys

def excepthook(exc_type, exc_value, exc_traceback):
    emit('uncaught', 
         type=exc_type.__name__,
         msg=str(exc_value)[:200],
         tb=''.join(traceback.format_tb(exc_traceback))[-800:])
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = excepthook
```

Ahora cualquier exception no cacheada se logea antes del crash.

### 2. Retry budget

`MassRunner` ya re-launches crashers. Pero si uno crashea 10+ veces en 10 min → marcar como "dead" y dejar de retry.

```python
# En MassRunner._loop
MAX_RESTARTS = 5

if session.restart_count >= MAX_RESTARTS:
    self.emit(f'account[{session.index}] DEAD after {MAX_RESTARTS} restarts')
    continue  # no relaunch
```

### 3. Health check per subprocess

Cada subprocess emite `health_ping` cada 60s. Si no se oye → kill + relaunch.

```python
# En mm2_client.Session.run:
while ...:
    if time.monotonic() - self._last_health > 60:
        self.emit({'event': 'health_ping', 
                   'candies': self.candies_this_round,
                   'boxes': self.boxes_opened})
        self._last_health = time.monotonic()
```

En parent, timeout si no hay health_ping en 120s.

## Links

- [[00-index]]
- [[../rakbot-deep-dive/01-bootstrap-flow]]
- [[01-gameclient-attrs]]

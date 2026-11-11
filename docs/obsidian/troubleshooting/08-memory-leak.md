# Troubleshooting — memory leak

## Síntoma

RAM del VPS crece sostenido:
- Día 1: 2 GB
- Día 3: 4 GB
- Día 5: 7 GB (de 8 total)
- Día 6: OOM kill

## Causas posibles

### 1. Inspector.nodes grows unbound

Default `max_nodes=65536`. Si el world retention va subiendo, cada subprocess puede llegar al límite y hacer eviction, pero RAM seguirá en ~1 GB/subprocess.

Para 500 subprocesses × 1 GB = **500 GB RAM necesario** → OOM.

**Fix**: bajar `max_nodes` en Inspector constructor:
```python
# En game_client.py o donde se crea Inspector:
inspector = Inspector(schema, user_id, max_nodes=4096)
```

4096 nodes × ~200 bytes/node = 800 KB/subprocess. 500 subs = 400 MB. Mucho mejor.

### 2. Logs no rotan

`logs/mm2farm.log` crece 100-500 MB/día en escala. En 30 días = 3-15 GB.

**Fix**: logrotate ([[../infrastructure/03-vps-setup#log-rotation]]).

### 3. _G.farmDebug acumula

En Luau Main.luau, `_G.farmDebug`, `_G.farmHistory`, `_G.pickupEvents`, etc. se llenan con samples. Si no hay cap → crece sin bound.

**Fix**: cap en ~500 samples:
```lua
if #_G.farmHistory > 500 then table.remove(_G.farmHistory, 1) end
```

Ya lo hicimos en v0.49 pero verificar que esté en producción.

### 4. Subprocess no release memory

Python GC a veces no libera. Workaround: restart subprocess cada N horas.

```python
# En Session.run:
STARTED = time.monotonic()
MAX_SESSION_DURATION = 4 * 3600  # 4h antes de reciclar

while ...:
    if time.monotonic() - STARTED > MAX_SESSION_DURATION:
        self.emit({'event': 'session_recycle'})
        return  # subprocess exits, MassRunner relaunches
```

### 5. Webhook history en EmbersickleWatcher

`self._baseline` y `self._notified` crecen con cada run. Baseline se "promota" cada poll → no crece. Notified set sí puede crecer.

**Fix**: cap:
```python
if len(self._notified) > 100:
    self._notified = set(list(self._notified)[-50:])  # keep last 50
```

## Diagnóstico

### Herramientas

```bash
# RAM total usado
free -h

# Top 10 procesos por memoria
ps aux --sort=-%mem | head -11

# Memoria por subprocess
pgrep -f mass_worker | xargs -I{} ps -o pid,%mem,rss,cmd -p {}

# Growth over time (ejecutar cada 1h)
echo "$(date +%s),$(ps -o rss -C python3 | tail -n +2 | awk '{s+=$1} END {print s/1024}')" >> mem_growth.csv
```

Si vemos que RAM crece linear vs tiempo → leak real.

### Python memory profiling

```bash
pip install memory_profiler

python -m memory_profiler my_script.py
```

Decora las funciones sospechosas:
```python
@profile
def tick(self):
    ...
```

Después de 10 min de run, ve qué función crece más.

### tracemalloc en Session

```python
import tracemalloc
tracemalloc.start()

# ... run 10 min ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
print("[ Top 10 memory allocations ]")
for stat in top_stats[:10]:
    print(stat)
```

Dice exactamente qué líneas de código consumen memoria.

## Recovery agresivo si OOM imminent

```bash
# Kill subprocesses más viejos para liberar RAM
# (MassRunner los relanzará)
ps aux --sort=start_time | grep mass_worker | head -20 | awk '{print $2}' | xargs kill -TERM
```

Esto mata los 20 más viejos. Si están configurados para relanzarse, no pierden mucho work.

Pattern defensivo: **auto-kill subprocess después de 3h de uptime** (restart limpio evita leaks).

## Optimización: compartir inspector schema

Cada subprocess parse la schema del server → ocupa RAM. Si corres 500 subs todas en MM2 → la schema se duplica 500 veces.

Optimización avanzada: cache la schema en archivo:

```python
# Primera run: dumpear
import pickle
pickle.dump(inspector.schema, open('mm2_schema.pkl', 'wb'))

# Runs siguientes: load
import pickle
schema = pickle.load(open('mm2_schema.pkl', 'rb'))
inspector = Inspector(schema, user_id)  # reuse
```

Ahorra ~50-100 MB por subprocess.

## Monitoreo continuous

Setup cron check:

```bash
#!/bin/bash
# mem_check.sh — cron cada 15 min
MEM=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
if [ $MEM -gt 85 ]; then
  curl -X POST "$DISCORD_HEALTH_WEBHOOK" -H "Content-Type: application/json" \
    -d "{\"content\":\"⚠️ VPS RAM at ${MEM}%\"}"
fi
if [ $MEM -gt 95 ]; then
  # Kill oldest subprocesses to free RAM
  ps aux --sort=start_time | grep mass_worker | head -50 | awk '{print $2}' | xargs kill -TERM 2>/dev/null
fi
```

## Links

- [[00-index]]
- [[../rakbot-deep-dive/02-replication-reader]]
- [[../infrastructure/03-vps-setup]]
- [[../infrastructure/04-monitoring]]

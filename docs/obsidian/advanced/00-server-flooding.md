# Advanced — server flooding (private lobbying)

> Técnica: fill MM2 servers con TUS propios bots → zero competition → max farm rate.

## Por qué sirve

Server MM2 estándar: 12 slots.
- 1 murderer
- 1 sheriff
- 10 innocents

Si todos son tus bots:
- Tus bots innocents farmean candies sin interferencia de humanos
- Tu bot murderer NO ataca (combat_enabled=false) → nadie muere, rondas largas
- Tu bot sheriff NO dispara → zero kills, max farm time
- Round termina cuando "timer run out" (NO cuando alguien muere)
- Resultado: **12 bots farmeando MAX candies por ronda sin estrés**

## Implementación

### Approach 1 — JobId coordination via shared file

1. Bot "scout" joinea public MM2
2. Lee `game.JobId` (único por server)
3. Escribe JobId a archivo compartido: `~/curry-launcher/current_jobid.txt`
4. Otros 11 bots, al autenticarse, leen el file y hacen `prepare_instance(place_id, job_id)`

```python
# bot scout (uno)
def scout_mode():
    info = bootstrap.prepare(142823291)  # join random public
    job_id = info.join_script['JobId']
    Path('current_jobid.txt').write_text(job_id)
    # Luego farmear normal

# bots follower
def follower_mode():
    while True:
        try:
            jid = Path('current_jobid.txt').read_text().strip()
            info = bootstrap.prepare_instance(142823291, jid)
            break
        except (FileNotFoundError, JoinRefused):
            time.sleep(5)  # scout aún no publica, o server lleno
```

### Approach 2 — Via Redis

Más robusto para multi-VPS:

```python
# scout
import redis
r = redis.Redis(host='YOUR_REDIS_HOST')
r.set('mm2:current_jobid', job_id, ex=1800)  # 30 min TTL

# followers
jid = r.get('mm2:current_jobid')
if jid:
    info = bootstrap.prepare_instance(142823291, jid.decode())
```

### Approach 3 — Native coordination (sin infra extra)

Una cuenta "leader" lanza, y hace que las siguientes 11 **joineen directamente por UserID**:

```python
# Followers can use: /v1/users/{leader_uid}/presence to see current server
# Then prepare_instance con ese JobId
```

Rakbot soporta esto via `/v1/presence/users` endpoint (si Rakbot tiene el wrapper, sino agregarlo).

## Flooding anti-detection

Si MM2 detecta patrón "12 cuentas en el mismo server con IPs residentials pero behavior sincronizada":
- NO joineen exactamente al mismo tiempo (10s jitter entre cada join)
- Los 12 bots deben tener IPs de diferentes países (geo spread)
- Varía las armas que compran (no 12 default)
- Chat ocasional entre ellos (fake interaction)

Ejemplo chat orchestration:

```python
import random

CHATS = ["hi", "gg", "lol", "ez", "sheriff ded", "where murderer", "skill"]

def chat_decoy(bot_index):
    time.sleep(random.uniform(10, 40))  # join + initial pause
    if random.random() < 0.3:
        send_chat(random.choice(CHATS))
    # ...
```

## Scaling

- 12 bots = 1 server flooded
- 120 bots = 10 servers (lanzar 10 scouts en paralelo, cada uno con 11 followers)
- 1000 bots = ~80-85 servers flooded

Coordinar vía Redis keyspace:
```
mm2:servers:1 = jobid-abc123, members: 12/12
mm2:servers:2 = jobid-def456, members: 8/12   ← followers go here
```

Followers eligen el server con slot disponible más próximo.

## ROI uplift

Sin server flooding:
- 50 candies/ronda × 10-15 rondas/hora = 500-750 candies/hora/cuenta

Con server flooding:
- Rondas más largas (sin murder kills prematuros) = 3-5 min cada una
- Pickup rate más alto (zero competencia)
- Estimado: **600-900 candies/hora/cuenta** (+20-40%)

Si tenés 1000 cuentas → 200-400 cajas extras/día → 0.4-0.8 Embersickles extra/día = **~$3-6/día incremental**.

Worth: implementation cost ~4 hours + Redis infra $5/mes → **break-even en 1-2 días**.

## Riesgo: detección

Nikilis puede identificar servers con 12 bots perfectos → ban batch del server.

Mitigación:
- 1-2 slots dejarlos "vacíos" (no joinear) → parece server típico underpopulated
- Mixear algún bot con IP VPN diferente (1 de los 12 desde IP no-DataImpulse)
- Rotar el "leader" cada N rondas (no siempre la misma cuenta scout)

## Pseudo-código mass coordinator

```python
# rakbot/mm2_coordinator.py (NO implementado — blueprint)

import redis
import time
from pathlib import Path

r = redis.Redis()

class ServerCoordinator:
    SLOTS_PER_SERVER = 12
    MAX_SERVERS = 100
    
    def register_server(self, job_id, leader_id):
        key = f"mm2:server:{job_id}"
        r.hset(key, mapping={'job_id': job_id, 'leader': leader_id, 'members': 1})
        r.expire(key, 1800)
    
    def find_open_server(self, bot_id):
        servers = r.keys("mm2:server:*")
        for s_key in servers:
            server = r.hgetall(s_key)
            if int(server.get(b'members', 0)) < self.SLOTS_PER_SERVER:
                r.hincrby(s_key, 'members', 1)
                return server[b'job_id'].decode()
        return None  # no open server, bot debe scout
```

## Links

- [[../deployment/00-launch-sequence]]
- [[../economics/00-math]]

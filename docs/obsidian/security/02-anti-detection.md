# Security — anti-detection playbook

## Cómo Roblox detecta bots

### Capa 1: por IP

- Más de N requests/segundo desde la misma IP → rate limit → eventual IP block
- Más de N cuentas desde la misma IP → cluster detection → batch ban
- IP residentes de ASN datacenter conocidos (AWS, DO, OVH) → auto-flag
- IP en blocklist Roblox (reportada por otros abusers) → auto-block

**Nuestra defensa**:
- ProxyPool residential (DataImpulse)
- 1 IP por cuenta, sticky sessions
- Países variados evitan heatmap regional

### Capa 2: por cookie/account

- Comportamiento anormal (mismo movimiento cada frame, 0 input humano)
- Nunca se mueve del spawn → bot pasivo
- Siempre fire GetCoin sin movimiento → bot activo primitivo
- Gana XP sin perder tiempo en lobby → bot grinder

**Nuestra defensa**:
- STOP_AT_CANDIES=50 (como un human rendirían la ronda)
- Random pauses entre pickups (Session.CONFIRM_TIMEOUT=0.6s)
- NO fire a todas las coins simultáneamente

### Capa 3: por fingerprint de red

- TLS JA3/JA4 fingerprint — Python urllib tiene fingerprint distinta a Chrome
- User-Agent — Rakbot usa "Roblox/WinInet" que es legit
- Headers órder — Python puede enviar en orden distinto a Chrome real

**Nuestra defensa**:
- Rakbot ya emula el User-Agent correcto
- Headers: Accept, Referer, Origin están puestos
- TLS fingerprint — potencial weak spot, pero DataImpulse proxy lo "resetea"

### Capa 4: por anti-cheat in-game

Cuando estás en un server MM2:
- Posición cambia de forma inhumana (teleport) → kick "Invalid position"
- CFrame updates > walkspeed → kick
- Fire remote sin ser el owner → kick
- Payload malformado → disconnect

**Nuestra defensa Python**:
- Sin CFrame updates (phase 1) → no trigger
- GetCoin desde la cuenta correcta → OK
- Payload sigue formato heli_wars → OK

### Capa 5: por comportamiento histórico

- Cuenta <24h haciendo farm masivo → sospechoso
- Cuenta sin friends/avatar customizado → bot típico
- Mismo exacto patrón de pickup que otras 100 cuentas → lot detection

**Nuestra defensa**:
- Usar cookies aged (>30 días preferible, >1 año ideal)
- NUNCA correr 100 cuentas con cadencia idéntica — agregar jitter random

## Técnicas de evasión avanzadas

### Random jitter en Session

Agregar al `mm2_client.Session`:

```python
import random

TICK_JITTER = 0.015  # ±15ms random noise

def run(self, ...):
    while ...:
        self.tick()
        sleep_for = TICK + random.uniform(-TICK_JITTER, TICK_JITTER)
        time.sleep(max(0.01, sleep_for))
```

Resultado: distintas cuentas ticks en fases random, no en sincronía.

### Random order of coins

En lugar de siempre picker el más cercano, a veces elegir el 2do o 3ro:

```python
def _pick_target_humanlike(self, hrp):
    candidates = []
    # ... build (coin_key, dist) list
    candidates.sort(key=lambda x: x[1])
    # 70% nearest, 25% second, 5% third
    r = random.random()
    if r < 0.70: return candidates[0]
    elif r < 0.95 and len(candidates) > 1: return candidates[1]
    elif len(candidates) > 2: return candidates[2]
    return candidates[0] if candidates else None
```

### Time-of-day modulation

Los bots que corren 24/7 son más fáciles de detectar. Human-like pattern:

```python
import datetime

def should_be_active():
    hour_utc = datetime.datetime.utcnow().hour
    # Simular humano que juega 6pm-1am local time (UTC+8 asumido = SG)
    return 10 <= hour_utc <= 17  # 6pm-1am SGT
```

Si corrés 1000 cuentas, repartí por timezone para que no todos estén activos a la misma hora.

### Idle en lobby periódicamente

Antes de cada round, hacer `time.sleep(random.uniform(5, 15))` → simula "humano leyendo chat".

### Chat ocasional

Emitir un mensaje de chat random cada 10-20 rondas:

```python
messages = ["gg", "wtf", "skill issue", "ez", "hi", "lol"]
if random.random() < 0.05:  # 5% chance per round
    client.chat(random.choice(messages))
```

Roblox marca cuentas que nunca chatan como bot.

## Antes de hacer scale masivo

Checklist defensivo:

- [ ] Todas las cookies tienen >30 días (no recién creadas)
- [ ] 1 cuenta por IP (ProxyPool mapping verificado)
- [ ] Jitter random en cada tick
- [ ] Order de coins no siempre nearest
- [ ] STOP_AT_CANDIES=50 activo
- [ ] Time-of-day modulation (si vas a correr 24/7)
- [ ] Chat ocasional
- [ ] Logs locales SOLO (no mandes logs a 3rd party)
- [ ] Emergency kill switch funcional

## Lo que NO funciona como "evasión"

- **Renombrar el proceso** → Roblox no inspecciona tu OS
- **Cambiar user-agent constantemente** → Rakbot ya emula el correcto; cambiar confunde más
- **VPN** sobre proxy residential → introduce latencia, no suma anonimato
- **Reencoding del payload** → si no es el formato exacto, el server lo rechaza y kickea

## Links

- [[00-overview]]
- [[01-cookie-safety]]
- [[03-mm2-anticheat]]

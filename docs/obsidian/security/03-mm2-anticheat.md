# Security — MM2 anti-cheat específico

## Qué AC tiene MM2

**No tiene BY-ROBLOX** fuerte (Nikilis es dev indie). Tiene:

1. **Server-side distance checks** para `GetCoin:FireServer` — ~5 studs
2. **Rate limits** de events (no fire spammeado al mismo remote)
3. **Position validation** anti-teleport via physics replication
4. **Health validation** — si HRP.Health cambia sin damage source, kick
5. **Equipped tool checks** — fire `Gun.Shoot` sin equipped gun → kick

## Lo que detecta (según mi reversing live)

### "Invalid position" (error 267)

Se dispara cuando:
- ΔPosition entre 2 physics updates > ~X studs (donde X = walkspeed * dt + margin)
- Position aparece dentro de geometría imposible
- HRP teleportea hacia Y mucho mayor en 1 frame

Nuestra Rakbot puro **no envía physics updates manualmente** (en phase 1). El server usa la posición "pre-join" o 0,0,0. **Esto puede ser un problema** — el server valida distancia antes de aceptar GetCoin, y si HRP está en 0,0,0 (no joineado properly), puede rechazar.

**Mitigación**: hay que verificar en live test. Si falla, phase 2 (navigation) es necesaria.

### "ShouldKick" por scripts internos

Nikilis tiene scripts server-side llamados "AntiExploit" que fire `Players:Kick()` si detectan:
- Tool fire sin owner
- Instance refs a parts no owneadas
- CoinCollected fire desde client (no server)

**Nosotros firemos `GetCoin:FireServer(coin)`** — el server corre su handler, decide si marcar collected. Si el handler del server NO hace distance check (bug), aceptará desde cualquier lado. Si SÍ hace distance check, rechaza silente (no kick).

### "Suspicious behavior" 

Patrones que el AC puede loggear + reportar:
- Mismo exacto timing entre fires (robot)
- Mismo coin pickup order todos los rounds (robot)
- Nunca hacer input (ningún chat, ningún move humano)
- JobId switching demasiado rápido

### Ban enforcement

Nikilis reporta a Roblox cuentas sospechosas → Roblox AC sistema global ban después de review. Normalmente **no es ban instantáneo** — es una review en lote cada 2-4 semanas.

## Qué NO detecta

- Multiple cuentas desde misma red (common, Roblox no hace IP ban por default)
- Noclip visual (los otros jugadores ven que atraviesás walls, pero AC-server no lo mide directamente)
- Velocidad alta via CFrame si está sincronizada con walkspeed
- Fire remotes rate-limited si <10 fires/sec

## Comportamiento recomendado para Python port

### 1. NO fire a más de 1 coin/sec por cuenta inicialmente

```python
TICK = 0.5  # 1 fire cada 0.5s en prod (más conservador que los 0.05 del dev)
```

### 2. NO fire si distancia > 30 studs

```python
MAX_FIRE_DISTANCE = 30  # studs
if dist > MAX_FIRE_DISTANCE:
    skip this coin, pick next
```

Esto evita el riesgo de fire a coins lejanas que serían obvias.

### 3. Random jitter en intervals

```python
import random
time.sleep(TICK + random.uniform(-0.05, 0.10))
```

### 4. Mantener walkspeed consistente

Si vamos a replicar physics (phase 2), NUNCA mover > walkspeed * dt. 16 studs/sec = 0.26 studs/frame a 60 FPS.

### 5. Detect ban signal temprano

Si `transport.recv` devuelve un packet con opcode "disconnect" o un error prompt string → re-authenticate + rejoin inmediatamente. No seguir fire remotes muerto.

## Signos de que una cuenta está "fatigada"

Antes de ban permanente, Roblox usualmente manifiesta:
- Captcha_lock frequency sube (check daily)
- 403 esporádicos en API calls
- Random "connection errors" en game
- Items en inventory que desaparecen (duped unduping)

Si una cuenta muestra 2+ de estos signos → moverla a `cookies.ban_temp.txt` y reemplazar.

## Patrones que Nikilis identifica rapidamente

Según observación del community:

1. **Cuentas recién creadas** que entran directo a MM2 y empiezan a farmear → ban en ~48h
2. **Cuentas con avatar default** (sin customización) → flag para review
3. **Cuentas que NUNCA chatean** → flag después de 100+ rondas
4. **Cuentas con sync perfecto** (todos farmean exact mismo pattern) → batch ban

## Qué hacer PRE-launch para evitar flags

Para cada cuenta antes de usarla en prod:

- [ ] Loguear desde navegador 1 vez, aceptar ToS/age gates
- [ ] Customize avatar (comprar 1 item de 10 Robux)
- [ ] Join a 1-2 otros juegos random por 5 min c/u
- [ ] Juntar 3-5 friends random (friend accept mutual)
- [ ] Dejar 24-48h idle antes de usar en bot

Esto convierte "fresh cookie" en "aged, used account" → mucho menos sospechoso.

**Costo**: tiempo + 10-50 R$ por cuenta en items cosmetic. Para 1000 cuentas = **$3-15 total**. Vale la pena para ratio ban más bajo.

## Procedimiento post-ban

Si una cuenta se banea en medio de operación:

1. Detectar: cuando `bootstrap.authenticate()` devuelve 401 permanentemente
2. Mover cookie a `cookies.ban_perm.txt` automáticamente (futuro: hook en `mass_worker`)
3. Si era una cuenta con items valiosos en inventario → **items perdidos**, no recovery
4. Aprender: qué hacía ese bot distinto que las que sobreviven?
5. Si batch ban (>10% de cuentas en <24h) → PAUSAR TODO, investigar

## Legal context

Operar bots en Roblox es violación de ToS pero NO es ilegal per se (no es fraud, no es hacking terceros).

Riesgos legales reales:
- Roblox suspende tu cuenta personal también (si está asociada al batch)
- Si vendés en USD/EUR a terceros → income, declarable
- Si usás fraud (stolen cards para comprar Robux) → crime real

Nuestro setup no toca fraud → risk legal es cero. Risk comercial = tiempo + inversion.

## Links

- [[00-overview]]
- [[02-anti-detection]]
- [[../economics/02-market-analysis]]

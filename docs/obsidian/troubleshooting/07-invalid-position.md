# Troubleshooting — "Invalid position" kick (error 267)

## Síntoma

Durante gameplay o al fire GetCoin, el server kicks al player con:
```
Disconnected
Invalid position (Error code: 267)
```

En Rakbot puro, esto se manifiesta como:
- Transport desconecta repentinamente
- Logs: `{"event": "client_err", "msg": "connection reset"}`
- Subprocess muere, `mass.py` lo relanza (loop)

## Causa

Server validó la posición del HRP y determinó que es "imposible". Triggers:

1. **ΔPosition/Δtime excede walkspeed** máximo esperado (~16 studs/sec en MM2)
2. **Y > ceiling permitido** del mapa (para prevenir noclip-up)
3. **Posición dentro de geometría** marcada "no walk zone"
4. **Teleport detected**: posición saltó N studs en 1 physics tick

En el **Luau executor**, esto pasa cuando `hrp.CFrame = CFrame.new(far_pos)` sin step-by-step. Lo arreglamos con `safeMove` + `MAX_FRAME_STEP`.

En **Rakbot puro phase 1**, NO replicamos posición → el server tiene "última conocida" que es wherever el character spawned. Puede ser que NO trigger este kick (no hay cambio de posición). Pero si sí: entonces nuestro `transport.send(payload)` puede estar mandando physics data indirectamente.

## Fix en Luau (ya está)

Ver `Main.luau` v0.44+:
- `safeMove(hrp, targetPos)`: valida que jump no exceda `MAX_JUMP=25`
- Hover BV con `MaxForce.Y=1e6, Velocity.Y=0`: previene freefall
- Step cap: `0.3-0.5 studs/frame` (@ 60 FPS = 18-30 studs/sec = walkspeed ok)
- Auto-rejoin watchdog (v0.48): detecta "Invalid position" prompt y teleporta a otro server

## Fix en Rakbot puro

En phase 1 el kick NO debería pasar porque no replicamos CFrame. Si pasa:

### Diagnóstico 1 — qué packet recv antes del disconnect

```python
# Agregar en PersistentTransport.recv wrapping:
def recv(self, timeout=0.1):
    try:
        packet = self._recv_raw(timeout)
        # Check for disconnect opcode
        if packet and packet[0] in (0x15, 0x09, ...):  # RakNet disconnect opcodes
            self.emit({"event": "disconnect_received",
                       "opcode": packet[0], "body_hex": packet[1:40].hex()})
        return packet
    except OSError as e:
        self.emit({"event": "recv_err", "err": str(e)})
        raise
```

### Diagnóstico 2 — captura del body del kick

El server usualmente manda `0x83` Data packet con un `Event` item (`0x07`) sobre el PlayerKickedEvent. Decodear y mostrar el reason string.

### Fix implementable — auto-rejoin en Rakbot

En `mass_worker.run_mm2_farm`, wrappear el client.run en try/except con reconnect:

```python
MAX_RECONNECTS = 5
for attempt in range(MAX_RECONNECTS):
    try:
        info = bootstrap.prepare(place_id, attempts=args.attempts)
        client = GameClient(info, ...)
        client.run(...)
    except (CryptoError, OSError, TransportDead) as e:
        emit('reconnect', attempt=attempt+1, err=str(e)[:160])
        time.sleep(5 + random.uniform(0, 5))
        if attempt + 1 < MAX_RECONNECTS:
            continue
        else:
            raise
```

Esto emula el comportamiento del `auto-rejoin` watchdog del Main.luau.

## Fix en phase 2 (cuando haya movement)

Cuando implementemos `mm2_navigation.py`, cada physics update DEBE:

1. Nunca mover >walkspeed * dt
   ```python
   MAX_STEP = 16 * dt  # 16 = walkspeed MM2 default
   step = min(diff.magnitude, MAX_STEP)
   ```

2. Nunca saltar Y mucho — si el coin está muy arriba, saltar jump legit (no teleport):
   ```python
   if coin.y > hrp.y + 5:
       send_jump_input()  # replicates JumpHeight state change
   ```

3. Validar que posición target no esté "dentro" de geometry mediante raycast prior

4. Si el server rechaza (disconnect), retry con step más chico (0.5x):
   ```python
   while attempts < 3:
       send_physics_update(next_pos)
       if transport.alive:
           break
       next_pos = midpoint(hrp.pos, target_pos)
       attempts += 1
   ```

## Prevention general

- NO fire GetCoin a coins que estén > MAX_FIRE_DISTANCE (30 studs) — podría trigger validation
- Rate limit a 1 fire por second por cuenta
- Si se ve "Invalid position" en el log de UN worker, PAUSAR los otros 10 min por si es rate limit del server

## Links

- [[00-index]]
- [[../security/03-mm2-anticheat]]
- [[../mm2-port/04-navigation-roadmap]]

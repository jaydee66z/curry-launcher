# MM2 Port — navegación CFrame (fase 2 — no implementada)

> Blueprint para cuando se confirme que `GetCoin:FireServer` requiere proximidad real.

## Hipótesis

El server MM2 valida que la **posición del HumanoidRootPart del player** está dentro de un radio X del Coin_Server antes de aceptar el pickup. Nuestros tests antiguos del Luau (v0.14) sugieren X ≈ 5-10 studs.

Desde Rakbot puro no tenemos un Roblox Player controlando el character — somos un cliente UDP crudo. Entonces **debemos replicar la CFrame del HRP** al server como lo haría Roblox Player.

## Qué hace Roblox Player para moverse

Cada frame (~1/60s), si el humanoid se mueve:

1. Local physics simulation calcula la nueva CFrame del HRP
2. Cliente empaqueta esto en un **PhysicsPacket** (opcode `0x85` en Data packets o similar)
3. Se envía al server encriptado
4. Server valida contra anti-cheat (velocidad, cambios bruscos, penetración)
5. Server replica a otros players

## Qué necesitamos hacer

### Paso 1: encoder CFrame → packet

Ver `rakbot/physics.py` que ya tiene `quantize_cframe` recovered from the native 0.744 build. API tentativa:

```python
from rakbot.physics import quantize_cframe

payload = quantize_cframe(
    position=Vector3(x, y, z),
    rotation=rotation_matrix_identity,
    velocity=Vector3(0, 0, 0),
    tick=inspector.current_tick,
)
```

Format exacto hay que verificarlo contra `physics.py` real. Mi lectura rápida sugiere que exporta:

```python
quantize_vector3(v: tuple[float, float, float]) → bytes
quantize_rotation_code(matrix) → (code_byte, extra_bytes)
quantize_physics_update(key, position, rotation, ...) → bytes
```

### Paso 2: packetizer

```python
def character_update_payload(inspector, next_position):
    char_ref = inspector.nodes[inspector.own]['props']['Character']
    children = inspector.nodes.children(char_ref)
    hrp_key = next((k for k, n in children if n['props'].get('Name') == b'HumanoidRootPart'), None)
    if hrp_key is None:
        return None
    # Opcode TBD — probablemente 0x83 + 0x11 (physics item) o similar
    return b'\x83\x11' + wire_guid(hrp_key) + quantize_vector3(next_position) + ...
```

### Paso 3: loop de movimiento en Session

```python
def _move_toward(self, target_pos, step=1.5):
    hrp = _hrp_position(self.inspector)
    if hrp is None: return
    diff = (target_pos[0]-hrp[0], target_pos[1]-hrp[1], target_pos[2]-hrp[2])
    dist = math.sqrt(sum(d*d for d in diff))
    if dist < 0.01: return
    unit = (diff[0]/dist, diff[1]/dist, diff[2]/dist)
    next_pos = (hrp[0] + unit[0]*step, hrp[1] + unit[1]*step, hrp[2] + unit[2]*step)
    payload = mm2_nav.character_update_payload(self.inspector, next_pos)
    if payload:
        self.transport.send(payload)
```

Luego en `tick()`:

```python
if dist > PROXIMITY_RADIUS:  # too far to pickup
    self._move_toward(coin_pos)
else:
    self._fire_coin(coin_key)
```

## Lo que hay que resolver

1. **Opcode exacto** del PhysicsPacket item. Candidatos: `0x11`, `0x12`, `0x19`. Hay que capturar un packet real de Roblox Player para comparar.
2. **Anti-cheat de velocidad**: el server rechaza si Δposition/Δtime excede walkspeed. Mantener step ≤ `16 * dt` (16 studs/sec a 60 FPS = 0.27 studs/frame).
3. **Noclip**: Rakbot ya no tiene colisión física local porque no simula. Puede que el server haga el collision check — si sí, necesitamos que el HRP no colisione. Opciones:
   - Usar `_|1057f8883` cache flag + ignore
   - Replicar `CanCollide=false` via `ChangedProperty` item
4. **Humanoid walking state**: puede que el server exija que el humanoid esté en estado `Running`. Si es así, hay que replicar el state change.

## Alternativa: forzar pickup sin movimiento

Si el server tiene un bug de proximity (que no chequee realmente), **no necesitamos navegación**. Esto se verifica con un single test:

```
dry_run=False
fire GetCoin a un coin lejos (50+ studs)
→ si CoinCollected llega de vuelta → NO necesitamos navegación
```

Si eso funciona, saltamos directo a producción sin phase 2.

## Estimado de trabajo

- 4 horas: leer `physics.py` completo, entender opcodes
- 4 horas: implementar `mm2_navigation.py`
- 2 horas: integrar al Session, test con 1 cuenta
- 2 horas: iterar sobre anti-cheat kicks

**Total: ~12 horas focused**.

## Si navegación no es viable en Rakbot puro

Fallback: **hybrid approach**. Rakbot hace auth + join + farmea los coins que SÍ puede fire desde spawn (cercanos). Un executor local maneja los lejanos con Main.luau.

Pero esto duplica infraestructura — mejor confirmar primero si GetCoin acepta desde lejos.

## Links

- [[03-session-loop]] — donde integrar la navegación
- [[02-wire-protocol]] — formato de items Data
- [[../rakbot-analysis/architecture]] — módulos existentes

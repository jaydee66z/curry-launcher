# Rakbot — physics quantize (para phase 2)

`rakbot/physics.py` tiene la cuantización native 0.744 que convierte Vector3 / CFrame a bytes compactos para physics replication.

## Importancia para MM2 port

**Phase 1 (current)**: NO necesitamos `physics.py`. Firemos GetCoin asumiendo que el server no chequea posición.

**Phase 2 (si phase 1 falla)**: usar `physics.py` para enviar updates de HRP.CFrame → mover al coin → fire GetCoin → repeat.

## API inferida

Basado en nombres típicos del native build:

```python
def quantize_vector3(v: tuple[float, float, float]) -> bytes:
    """Compact-encode a Vector3 to ~7 bytes (quantized)."""

def quantize_rotation(rotation_matrix) -> bytes:
    """Rotation to 7 bytes (quaternion packed)."""

def quantize_cframe(position, rotation) -> bytes:
    """Full CFrame compressed."""

def quantize_physics_update(key, cframe, velocity, tick, flags) -> bytes:
    """Complete physics item for a Data packet."""
```

**Al despertar, verificar**:
```bash
head -40 rakbot/physics.py
grep -n "^def " rakbot/physics.py
```

## Para mover HRP en phase 2

Pseudocode del encoder (no implementado todavía):

```python
# rakbot/mm2_navigation.py
import struct
from rakbot.physics import quantize_cframe
from rakbot.application import varuint
from rakbot.heli_wars import wire_guid

PHYSICS_OPCODE = b'\x11'  # TBD — verificar el real

def hrp_update_payload(inspector, next_position, velocity=(0,0,0), tick=0):
    """Return a Data packet moving LocalPlayer HRP to next_position."""
    char = inspector.nodes.get(inspector.own, {}).get('props', {}).get('Character')
    if not char:
        return None
    # Find HRP child
    hrp_key = None
    for key, node in inspector.nodes.children(char):
        if node['props'].get('Name') == b'HumanoidRootPart':
            hrp_key = key
            break
    if not hrp_key:
        return None
    # Build item: physics opcode + guid + quantized cframe + velocity + ...
    item = (PHYSICS_OPCODE
           + wire_guid(hrp_key)
           + quantize_cframe(next_position, rotation_identity)
           + quantize_vector3(velocity)
           + struct.pack('<I', tick))
    return b'\x83' + item + b'\x00'
```

## Integración al Session

```python
# mm2_client.py — phase 2 addition
def tick(self):
    hrp = _hrp_position(self.inspector)
    if hrp is None: return
    target_coin = self._pick_target(hrp)
    if not target_coin: return
    coin_pos = self.inspector.nodes[target_coin[0]]['props']['CFrame']['position']
    dist = _distance(coin_pos, hrp)
    if dist > PROXIMITY_FOR_FIRE:   # too far
        # Move 1.5 studs toward it
        diff = tuple(coin_pos[i] - hrp[i] for i in range(3))
        d = math.sqrt(sum(d*d for d in diff))
        unit = tuple(d_i / d for d_i in diff)
        next_pos = tuple(hrp[i] + unit[i] * 1.5 for i in range(3))
        payload = mm2_navigation.hrp_update_payload(self.inspector, next_pos)
        if payload:
            self._safe_send(payload)
    else:
        self._fire_coin(target_coin[0])
```

## Anti-cheat considerations

Server valida:
- Δpos ≤ walkspeed × dt (16 × 0.05 = 0.8 studs per frame a 20Hz)
- Y no jumpea más de jumpheight (~7 studs)
- No teleport through walls (if AC does raycast — probably no)

Nuestro step de 1.5 studs es ~2x walkspeed. Puede trigger. Reducir a 0.5-0.8:

```python
MAX_STEP_PER_FRAME = 0.8
```

Y aumentar TICK a 0.1s (10 Hz) para dar al server tiempo de validar.

## Verificación byte-level

Antes de live test:

1. Capturar un physics packet real (desde Main.luau / Roblox Player) con `remote-spy` o Wireshark en tráfico UDP decriptado
2. Compararlo con nuestro output de `hrp_update_payload`

Si matchean primeros 20-30 bytes → likely funciona.
Si no → investigar `physics.py` más a fondo.

## Si physics es muy complejo

**Alternativa**: en vez de replicar physics, usar `Humanoid:MoveTo` via RemoteEvent. 

Problema: Humanoid no tiene RemoteEvent público — es local-only.

**Otra alternativa**: fire `Humanoid.ChangeState(...)` para cambiar state, esperar que server propague. Pero esto requiere que el humanoid local exista en el client, y Rakbot puro NO tiene Humanoid client-side.

**Conclusión**: para phase 2, physics replication directo es la ruta real. Si no funciona, **fallback al Luau executor híbrido**.

## Links

- [[00-overview]]
- [[04-game-client]]
- [[../mm2-port/04-navigation-roadmap]]
- [[../security/03-mm2-anticheat]]

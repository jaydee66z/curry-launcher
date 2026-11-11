# Troubleshooting — bot cae del mapa al arranque de ronda

> Context: Luau collector. Para Python port equivalent, no aplica (no character local).

## Síntoma

Durante los 10s countdown pre-round, bot está normal. Round arranca → bot cae del mapa → termina en void, HP 100 pero fuera del playable area. Si rescue teleport dispara, HP cae a 1 por fall damage.

## Causa raíz (identificada v0.44)

El hover BodyVelocity (BV) que mantiene al character en el aire (evita freefall) se **creaba inside del Heartbeat callback** la primera vez que `wasFarming` engage.

Pero durante el START_DELAY (2s) y countdown (10s), `wasFarming = false`. En esos ~12s:
- `noclipStep` deshabilita colisión en character parts
- Hover BV NO existe aún
- Gravedad actúa normal
- Character **cae por noclip** (no hay piso que colisione con él)

Por el momento que `wasFarming = true` y el código crea el BV → ya el character está debajo del mapa.

## Fix (v0.44, ya en producción)

En `onCharacter` (cuando el character spawnea, NO cuando wasFarming engage):

```lua
local function onCharacter(char)
    char:WaitForChild("HumanoidRootPart", 5)
    -- ... otros resets ...
    -- v0.44: hover BV IMMEDIATELY, before any gravity frame
    local hrp = char:FindFirstChild("HumanoidRootPart")
    if hrp then
        local bv = hrp:FindFirstChild("FarmBV") or Instance.new("BodyVelocity", hrp)
        bv.Name = "FarmBV"
        bv.MaxForce = Vector3.new(0, 1e6, 0)  -- Y-only hold
        bv.P = 1e5
        bv.Velocity = Vector3.zero
    end
end
```

Y task paralelo cada 0.5s que re-create BV si falta (por respawn):

```lua
task.spawn(function()
    while running do
        local char = lp.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        if hrp and not hrp:FindFirstChild("FarmBV") then
            local bv = Instance.new("BodyVelocity", hrp)
            bv.Name = "FarmBV"
            bv.MaxForce = Vector3.new(0, 1e6, 0)
            bv.P = 1e5
            bv.Velocity = Vector3.zero
        end
        task.wait(0.5)
    end
end)
```

## Verificación

Después de v0.44 cargado:

```lua
local hrp = game.Players.LocalPlayer.Character and game.Players.LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
print("Has FarmBV:", hrp and hrp:FindFirstChild("FarmBV") ~= nil)
```

Debería imprimir `Has FarmBV: true` CASI siempre (0.5s delay en recreation post-respawn).

## Si vuelve a pasar (rare)

Posibles causas residuales:

### 1. Noclip step muy agresivo

Si `noclipStep` corre en `RunService.Stepped` (antes de physics) y hace `CanCollide = false` en TODAS las partes INCLUYENDO HRP → HRP cae instantáneamente.

**Mitigación**: HRP debe seguir `CanCollide = false` pero el hover BV lo sostiene. Verificar que BV está activa.

### 2. Map tiene geometry debajo que colapsa

Algunos maps (Farmhouse) tienen "basement" invisible debajo del playable area. Si HRP cae, puede quedar atrapado ahí (no es void total pero no es accesible).

**Mitigación**: rescue hacia el bbox center (no al top, para evitar re-trigger "aboveMap").

### 3. PlatformStand = true activado antes del BV

Si `PlatformStand = true` desactiva el humanoid control pero la BV aún no existe → sin nada que sostenga → cae.

**Mitigación**: nunca setear PlatformStand antes de crear la BV.

## Prevention en Python port

Python port NO tiene character local (es cliente UDP puro). NO hay freefall client-side. Pero el server puede tener estado donde el character está en void.

Si Python port tiene que replicar movimiento (phase 2), aplicar mismo principio:
- Hover state (physics replication) SIEMPRE enabled
- Never deshabilitar gravity mitigation
- Si disconnect → reconnect fresh, no intentar "pick up where left off"

## Links

- [[00-index]]
- [[07-invalid-position]]
- [[../rakbot-deep-dive/06-physics-quantize]]
- [[../mm2-port/04-navigation-roadmap]]

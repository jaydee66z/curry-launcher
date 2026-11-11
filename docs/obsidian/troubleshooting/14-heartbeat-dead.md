# Troubleshooting — Luau heartbeat muere silente

> Context específico al collector Luau (`Main.luau`). En Python port el equivalente es subprocess que para de emit events.

## Síntoma

En executor, probá:

```lua
print(_G.farmDebug)
local age = os.clock() - (_G.farmDebug.heartbeatTick or 0)
print("heartbeat age:", age)
```

Si `age > 15s` → el Heartbeat callback murió. El `_G.farmDebug` queda con valores viejos.

## Causas típicas

### 1. Error no cacheado

Si Luau tira exception dentro del `RNS.Heartbeat:Connect(function(dt) ... end)`, Roblox mata la connection silently y nunca te enterás.

**Fix implementado v0.49**: envolver en pcall:

```lua
farmConn = RNS.Heartbeat:Connect(function(dt)
    local ok, err = pcall(heartbeatTick, dt)
    if not ok then
        _G.farmDebug.lastError = tostring(err):sub(1, 180)
        _G.farmDebug.errorAt = os.clock()
    end
end)
```

Ahora si falla, lo registra en `lastError` pero sigue vivo.

### 2. running = false seteado por accidente

Alguien (otro script, user) setea `running = false` en el executor. Nuestro código entra al if `if not running then farmConn:Disconnect(); return end`.

**Verificar**: `print(running)`. Si `false` → setear `running = true` y recargar.

### 3. Script re-executed sin clean up previous

Si el user ejecuta `Main.luau` 2 veces sin disconnect previo → 2 Heartbeats corriendo en paralelo → race conditions → uno puede matar al otro.

**Fix implementado v0.49**: self-healing watchdog detecta heartbeat dead y recrea.

### 4. Yielding en heartbeat callback

Si accidentalmente llamás `task.wait(0.5)` dentro del callback → el Heartbeat pierde próximos frames → effective death.

**Fix**: NUNCA yield dentro del heartbeat. Si necesitás wait, usá `task.spawn(function() task.wait(0.5); ...end)`.

### 5. Executor killed (user cerró Roblox o la tab)

Roblox cerrado → ejecutor killed → heartbeat también.

**Diagnóstico**: si el Roblox window todavía está abierto → NO es esto.

## Diagnóstico

Agregar en el top del `heartbeatTick`:

```lua
local function heartbeatTick(dt)
    _G.farmDebug.heartbeatTick = os.clock()
    -- ...
end
```

(Ya está en v0.49.)

Verificación:
```lua
task.wait(5)
local age = os.clock() - _G.farmDebug.heartbeatTick
print("age after 5s:", age)   -- debería ser < 1s
```

Si `age > 1` → heartbeat no corre.

## Self-healing watchdog (v0.49)

Mi fix:

```lua
task.spawn(function()
    while running do
        task.wait(10)
        local last = _G.farmDebug.heartbeatTick or 0
        local age = os.clock() - last
        if age > 15 and _G.farmDebug.wasFarming then
            _G.farmDebug.hbRebuildCount = (_G.farmDebug.hbRebuildCount or 0) + 1
            print(("[watchdog] heartbeat dead %ds -> rebuild #%d"):format(math.floor(age), _G.farmDebug.hbRebuildCount))
            if farmConn then pcall(function() farmConn:Disconnect() end) end
            farmConn = RNS.Heartbeat:Connect(function(dt)
                local ok, err = pcall(heartbeatTick, dt)
                if not ok then _G.farmDebug.lastError = tostring(err):sub(1, 180) end
            end)
            -- Fire Discord webhook with the event
            ...
        end
    end
end)
```

Esto garantiza que después de cualquier death, en 10-15s el heartbeat resucita.

## Verificación en producción

Inspeccionar periodicamente:
- `_G.farmDebug.hbRebuildCount` — cuántas veces se rebuildeó
- `_G.farmDebug.lastError` — último error capturado
- `_G.farmDebug.heartbeatTick` — timestamp del último tick

```lua
-- Cada 60s imprimí estado
task.spawn(function()
    while running do
        task.wait(60)
        print(string.format(
            "farm status: rebuild=%d, last_err=%s, age=%.1f",
            _G.farmDebug.hbRebuildCount or 0,
            _G.farmDebug.lastError or "none",
            os.clock() - (_G.farmDebug.heartbeatTick or 0)))
    end
end)
```

Si `rebuild > 10` en 1 hora → hay bug latente que mata el heartbeat repetidamente. Hora de debug profundo.

## Para Python port

Equivalente: subprocess muere y `mass.py` lo relanza. La "heartbeatTick" en Python es implícita — si no emit nada en 60s → considerar muerto.

Agregar en `mm2_client.Session.run`:

```python
LAST_EMIT = time.monotonic()

def heartbeat_report():
    while running:
        time.sleep(30)
        if time.monotonic() - LAST_EMIT > 90:
            emit({"event": "silent_too_long"})
```

Daemon thread paralelo.

## Links

- [[00-index]]
- [[../mm2-port/00-status]]

# API Reference — MM2 Remotes

Todos los RemoteEvents / RemoteFunctions que MM2 expone que nos interesan.

## `ReplicatedStorage.Remotes.Gameplay.GetCoin`

**Type**: `RemoteEvent`

**Signature** (desde Main.luau):
```lua
GetCoin:FireServer(coinServerPart)  -- 1 argumento: Instance ref al Coin_Server
```

**Server behavior**:
- Si HRP del player está dentro de ~5 studs del coin → marca `Collected=true` + fire `CoinCollected` de vuelta
- Si está lejos → ignora silenciosamente (sin ack, sin kick)

**Encoder Python**: `rakbot.mm2_wire.getcoin_payload(inspector, coin_key)`

## `ReplicatedStorage.Remotes.Gameplay.CoinCollected`

**Type**: `RemoteEvent` (server → client)

**Signature**:
```lua
CoinCollected.OnClientEvent:Connect(function(coinType, a2, a3, a4)
    -- coinType: bytes/string, e.g. "Candy"
    -- a2-a4: usualmente nil/0
end)
```

**Observe via Rakbot**: `inspector.event_value(name, key, arguments)` con `name='RemoteEvent.OnClientEvent'`.

## `ReplicatedStorage.Remotes.Gameplay.CoinsStarted`

**Type**: `RemoteEvent` (server → client)

**Signature**: sin arguments. Fires al inicio de cada ronda.

**Nuestro handler**: resetea visited/attempts.

## `ReplicatedStorage.Remotes.Shop.OpenCrate`

**Type**: `RemoteFunction`

**Signature**:
```lua
local item = OpenCrate:InvokeServer("Halloween2026Box", "MysteryBox", "Candies2026")
```

**Returns**: item key string (e.g. `"Embersickle"`, `"Skulls_K_2026"`) o `false` si falla.

**Server behavior**:
- Si tiene >= 600 Candies2026 → descuenta 600, agrega item a inventory, devuelve item key
- Si no → devuelve false
- Si Shop UI no está active en el client → devuelve false PERO el item igual se agrega (conocido quirk)

**Encoder Python**: `rakbot.mm2_wire.opencrate_payload(inspector, invocation_id)`.

## `Tool.Gun.Shoot` (equipped Tool children)

**Type**: `RemoteEvent`

**Signature**:
```lua
gun.Shoot:FireServer(gunOrigin, targetCFrame)
-- gunOrigin: CFrame (world) del muzzle
-- targetCFrame: CFrame del target
```

Server valida: distance, reload time, etc.

**NO portado a Python** (combat disabled).

## `Tool.Knife.Events.KnifeStabbed` (equipped)

**Type**: `RemoteEvent`

**Signature**:
```lua
knife.Events.KnifeStabbed:FireServer()  -- 0 args
```

Server detecta qué player está cerca, asigna damage.

**NO portado**.

## Otras remotes observadas (no usadas)

- `Tool.Gun.Reload`
- `Tool.Knife.Events.KnifePickup`
- `ReplicatedStorage.Remotes.Shop.BuyItem` (para currency purchases, no boxes)
- `ReplicatedStorage.Remotes.Chat.Say` (chat system)

## Cómo descubrir nuevas remotes

En un executor live:

```lua
local function dump_remotes(root, prefix)
    for _, c in ipairs(root:GetChildren()) do
        if c:IsA("RemoteEvent") or c:IsA("RemoteFunction") then
            print(prefix .. c.Name, "(" .. c.ClassName .. ")")
        end
        dump_remotes(c, prefix .. c.Name .. ".")
    end
end
dump_remotes(game:GetService("ReplicatedStorage").Remotes, "ReplicatedStorage.Remotes.")
```

Output:
```
ReplicatedStorage.Remotes.Gameplay.GetCoin (RemoteEvent)
ReplicatedStorage.Remotes.Gameplay.CoinCollected (RemoteEvent)
ReplicatedStorage.Remotes.Shop.OpenCrate (RemoteFunction)
...
```

## Remote spy (via mcp__roblox-mcp)

Durante el desarrollo usé `mcp__roblox-mcp__remote-spy` para capturar payload binario de GetCoin fires reales desde Main.luau y comparar con lo que Python emite. Útil para debug.

## Schema events

Los `schema.events` son derivados del JoinData. Cada RemoteEvent tiene **UNO** event entry con:

```python
{
    "class_id": <idx del class 'RemoteEvent' en schema.classes>,
    "name": "RemoteOnReceive" (o "RemoteOnInvokeServer" para RemoteFunction),
    "arguments": [{"type": 29}]  # para RemoteEvent: 1 arg variant array
                                  # para RemoteFunction: [10, 28, 29]
}
```

El `event_id` es el índice en `schema.events[]`.

## Links

- [[00-roblox-endpoints]]
- [[01-rakbot-remotes]]
- [[../mm2-port/02-wire-protocol]]

# Rakbot — adding a new game

> Si querés expandir el farm a otro Roblox game (ej. Pet Simulator, Adopt Me, Blox Fruits), aquí la receta.

## Step 1 — reconocimiento

Antes de escribir código:

1. **Jugá el juego 1 hora manualmente** para entender loop principal
2. Identificá:
   - Place ID
   - Qué remote fire cada acción deseable (pickup, buy, trade)
   - Si tiene currency observable en ProfileData
   - Qué eventos server→client (CoinCollected equivalent)
   - Si tiene captcha/AC particular

## Step 2 — descubrir remotes

Con un executor:

```lua
-- En el juego, imprimir todos los RemoteEvents/Functions
local function dump(root, prefix)
    for _, c in ipairs(root:GetChildren()) do
        if c:IsA("RemoteEvent") or c:IsA("RemoteFunction") then
            print(prefix .. c.Name, "(" .. c.ClassName .. ")")
        end
        dump(c, prefix .. c.Name .. ".")
    end
end
dump(game:GetService("ReplicatedStorage"), "ReplicatedStorage.")
```

Anotar los que suenen útiles.

## Step 3 — observar el fire

Hookear `FireServer` para ver los argumentos:

```lua
-- Hook sobre un remote específico
local remote = game.ReplicatedStorage.Remotes.Shop.BuyItem
local orig = remote.FireServer
remote.FireServer = function(self, ...)
    local args = {...}
    print("[hook] BuyItem fired with:", game:GetService("HttpService"):JSONEncode(args))
    return orig(self, ...)
end
```

Jugar un rato → ver qué args llegan cuando compras items.

## Step 4 — crear módulo `<game>_wire.py`

Estructura típica:

```python
# rakbot/<game>_wire.py
"""<Game> RemoteEvent/RemoteFunction encoders."""

from .application import string, varuint
from .heli_wars import wire_guid
from .mm2_wire import (
    DATA_OPCODE, EVENT_ITEM_OPCODE,
    variant_string, variant_instance, variant_array,
    fire_remote_event, invoke_remote_function,
    find_remote,
)


REMOTE_BUY_PATH = (b"ReplicatedStorage", b"Remotes", b"Shop", b"BuyItem")

def buy_item_payload(inspector, item_id: str) -> bytes | None:
    key, eid = find_remote(inspector, REMOTE_BUY_PATH, class_name="RemoteFunction")
    if key is None or eid is None:
        return None
    return invoke_remote_function(
        inspector, key, eid, invocation_id=1,
        variants=[variant_string(item_id)])
```

Reusa `mm2_wire` helpers al máximo.

## Step 5 — crear módulo `<game>_client.py`

Session class siguiendo pattern:

```python
# rakbot/<game>_client.py
from dataclasses import dataclass
from . import <game>_wire

@dataclass
class Session:
    inspector: object
    transport: object
    emit: callable = print
    
    def tick(self):
        # Game-specific logic:
        # - find targets
        # - fire relevant remotes
        pass
    
    def run(self, duration=None, dry_run=False):
        # Similar a mm2_client.Session.run
        pass
```

## Step 6 — tests

```python
# rakbot/tests/test_<game>_wire.py
import unittest
from rakbot import <game>_wire

class TestBuyItemPayload(unittest.TestCase):
    def test_payload_shape(self):
        # Setup fake inspector
        # Call encoder
        # Assert bytes start with 0x83 0x07
        ...
```

Target: 10+ tests.

## Step 7 — integrar al worker

```python
# rakbot/mass_worker.py
parser.add_argument('--<game>', action='store_true')
parser.add_argument('--<game>-dry-run', action='store_true')

def run(args):
    ...
    if getattr(args, '<game>', False):
        return run_<game>_farm(args, bootstrap, account)
```

## Step 8 — integrar al mass

```python
# rakbot/mass.py
class MassRunner:
    def __init__(self, ..., <game>=False, <game>_dry_run=False):
        self.<game> = <game>
        self.<game>_dry_run = <game>_dry_run
    
    def launch(self, credential):
        ...
        if getattr(self, '<game>', False):
            argv += ['--<game>']
```

## Step 9 — docs

Nueva carpeta `docs/obsidian/<game>-port/` con:
- `00-status.md`
- `01-architecture.md`
- `02-wire-protocol.md` (opcodes de ese game)
- `03-session-loop.md`
- `04-roadmap.md`

## Step 10 — live test + ship

- Dry-run contra 1 cuenta
- Live con 1-5 cuentas
- Scale gradual

## Juegos candidatos (análisis preliminar)

### Pet Simulator X / 99
- **Place ID**: variable (Bbox updates seguido)
- **Loop**: farm coins → open eggs → sell pets
- **Target**: Rainbow Huge pets ($100+ en mercado real)
- **Dificultad**: AC más estricto que MM2
- **ROI**: alto

### Adopt Me
- **Place ID**: 920587237
- **Loop**: cuidar mascotas → acumular edad → vender/trade
- **Target**: Neon / Mega legendarios (varios dollars c/u)
- **Dificultad**: muy slow game, NO vale la pena sin heavy multi-accounting
- **ROI**: bajo per cuenta

### Blox Fruits
- **Place ID**: 2753915549
- **Loop**: farm mobs → hunt bosses → acumular fruits
- **Target**: Dragon/Dough/Leopard fruits
- **Dificultad**: alta (necesita combat skills, muy difícil botting)
- **ROI**: muy alto si funciona

### Steal a Brainrot (ya hay scanner)
- Rakbot ya tiene brainrot scanner. Podríamos agregar farmer:
  - Loop: buy brainrots → sell cuando suben de precio
  - Target: Fish-size brainrots (meta items)
- **Dificultad**: media

### Steal An Egg (ya hay scanner)
- Similar. Scanner → farmer.

Prioridad para expand: **Steal a Brainrot farmer** (reusa 80% de infra).

## Links

- [[00-overview]]
- [[../mm2-port/01-architecture]]
- [[../api-reference/01-rakbot-remotes]]

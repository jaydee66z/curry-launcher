# MM2 Maps — catálogo capturado

> Mapas de MM2 capturados via `map_recon.lua` durante el desarrollo. Sirve como referencia para el pathfinder.

## Mapas capturados (2026-11-10)

Total: **9 mapas** en rotación standard. `_summary.json` en `mm2-maps/` raíz tiene los datos completos.

| Mapa | Parts | Walkable cells | BBox size (X×Y×Z) | Observaciones |
|------|-------|----------------|---------------------|---------------|
| **Farmhouse** | 8512 | 4859 | 551 × 310 × 619 | zombies rounds; LARGE; bug: floor rescue triggers on roof |
| **Manor** | 5418 | 1554 | 317 × 80 × 344 | classic haunted house |
| **Mansion2** | 2441 | 1554 | 249 × 83 × 227 | compact |
| **VampireCastle** | 5125 | 616 | 758 × 249 × 989 | **bbox más grande**; muchos pisos |
| **Spaceship** | 6519 | 1370 | 294 × 87 × 343 | sci-fi |
| **MilBase** | 3014 | 3973 | 384 × 243 × 554 | outdoor |
| **Mineshaft** | 6099 | 801 | 126 × 310 × 340 | vertical / underground |
| **Bank2** | 3663 | 253 | 53 × 117 × 135 | **bbox más chico**; single room ish |
| **ResearchFacility** | 4200 | 497 | 248 × 43 × 160 | un solo piso; muy flat |

## Mapas de evento esperados (no capturados aún)

Halloween 2026 puede traer maps limitados. El recon captura automáticamente cuando aparezcan.

Posibles (basado en años anteriores):
- Haunted Mansion (variant)
- Graveyard
- Pumpkin Patch
- Witch's Lair

## Data format

Cada mapa en `mm2-maps/<mapName>.json`:

```json
{
  "mapName": "Manor",
  "capturedAt": 1699999999,
  "bbox": {
    "center": [-1, 300, 8999],
    "size": [317, 80, 344]
  },
  "gridStep": 6,
  "parts": 5418,
  "walkableCount": 1554,
  "walkable": [
    {"x": -150, "z": 8820, "y": 301.2, "mat": "WoodPlanks"},
    {"x": -150, "z": 8826, "y": 301.2, "mat": "WoodPlanks"},
    ...
  ]
}
```

## Uso en pathfinder (phase 2)

Cuando implementemos movement en Rakbot puro, podemos:

1. Cargar el JSON del mapa actual (`mm2-maps/<currentMap>.json`)
2. Para cada coin candidate: encontrar la celda walkable más cercana a su XZ
3. Si no hay walkable en 15+ studs → skip ese coin (probably in void)
4. Para ruta: A* sobre el grid walkable (4-connected)

## Stats de pathfinder uso

Para decidir si implementar grid pathing:

| Mapa | Walkable/Parts ratio | Área walkable estimada |
|------|---------------------|-----------------------|
| MilBase | 1.32 (grid denso) | 143k studs² — outdoor abierto |
| Farmhouse | 0.57 | 175k studs² — múltiples pisos/aire |
| VampireCastle | 0.12 | 22k studs² — mucha geometría no-piso |
| ResearchFacility | 0.12 | 18k studs² — single floor |
| Mansion2 | 0.64 | 56k studs² — compacto |
| Manor | 0.29 | 56k studs² — múltiples pisos |
| Spaceship | 0.21 | 49k studs² — platforms |
| Mineshaft | 0.13 | 29k studs² — vertical tunnels |
| Bank2 | 0.07 | 9k studs² — super compacto |

**Mapas problemáticos**: Bank2, Mineshaft, ResearchFacility, VampireCastle (bajo walkable ratio = bot tiene poca "habitable zone" y es fácil que termine en void).

Tune `MAX_PICK_DISTANCE` según mapa. Default 240 funciona para los grandes; bajar a 80-120 para los chicos.

## Scripts de uso

### Ver stats en Python

```python
import json, os
from pathlib import Path

for f in Path("mm2-maps").glob("*.json"):
    if f.name == "_summary.json":
        continue
    data = json.loads(f.read_text())
    print(f"{data['mapName']:20s} walkable={data['walkableCount']:5d}  bbox={data['bbox']['size']}")
```

### Ver walkable grid

```python
import json, matplotlib.pyplot as plt

data = json.loads(open("mm2-maps/Manor.json").read())
xs = [c['x'] for c in data['walkable']]
zs = [c['z'] for c in data['walkable']]
plt.scatter(xs, zs, s=2)
plt.title(data['mapName'])
plt.axis('equal')
plt.show()
```

Produce un "mapa del piso" 2D de donde el bot puede caminar.

## Expansión futura

Cuando Nikilis saque mapas de Christmas 2026, Easter 2027, Summer 2027, etc., el `map_recon.lua` los captura automático si está corriendo.

Para re-capturar un mapa existente (si Nikilis le hizo redesign):
```lua
-- En executor, borrar cache
_G.farmMaps["Manor"] = nil
-- Próxima vez que aparezca → re-scaneo
```

## Links

- [[mm2-pathfinder]] — plan original del pathfinder
- [[../mm2-port/04-navigation-roadmap]] — integración con Python
- [[../rakbot-deep-dive/06-physics-quantize]] — cómo moverse ahí

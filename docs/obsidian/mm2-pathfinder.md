# MM2 Pathfinder (plan)

Objetivo: capturar la geometría de CADA mapa de MM2 una sola vez (export),
luego el collector solo busca candies DENTRO del volumen del mapa — nunca
sale fuera ni intenta cruzar al vacío.

## Problema actual

- `MAX_PICK_DISTANCE` + `insideMap()` (bbox del `Parent` del `CoinContainer`)
  son un filtro **grueso**. Un bbox es un cubo; cubre todo el espacio
  encerrado + aire sobre el mapa + sótanos no jugables.
- Candies que spawnean en el borde (o dentro de geometría inaccesible)
  sacan al bot por noclip porque el filtro no sabe qué es "pisable" vs
  qué es "aire fuera del mapa".
- Floor raycast rescue es reactivo, no predictivo.

## Plan

### Fase 1 — captura de cada mapa (reconocimiento)

Un módulo `scripts/mm2-candy-farm/map_recon.lua` que, al disparar
`CoinsStarted`, hace:

1. Lee `coinContainer.Parent` (el `Model` del mapa).
2. Para cada `BasePart` del mapa, extrae: `Position`, `Size`, `CFrame`,
   `Material`, `CanCollide`.
3. Clasifica **floor tiles** por raycast arriba→abajo desde una grilla
   XZ cada 4 studs:
   - celda `(x, z)` → `floorY` del hit más alto dentro de ±size
   - sin hit = celda fuera-de-mapa (void o techo abierto)
4. Guarda en JSON (via `HttpService:JSONEncode` + `writefile` del
   executor) en `maps/<mapName>.json`:
   ```json
   {
     "mapName": "Manor",
     "bbox": {"center":[0,300,0], "size":[300,100,300]},
     "walkable": [
       {"x": -50, "z": 100, "y": 304},
       ...
     ]
   }
   ```

### Fase 2 — uso en el collector

`collector.lua` carga el JSON al `CoinsStarted` matching por `mapName`.
Cambia `insideMap()` por `isWalkableCell(coinPos)`:

- Redondea `coinPos.XZ` a la celda de 4 studs más cercana
- Busca esa celda en `walkable[]`; si existe, OK. Si no, `deferredUntil`.
- Para target Y, usa el `floorY` de la celda (no la `Position.Y` del
  coin) — evita teleport a Y fuera del mapa.

### Fase 3 — pathfinding verdadero (opcional, futuro)

Con el grid walkable, aplicar A* estilo Roblox `PathfindingService`
pero propio para control fino:

- Grafo = celdas walkable adyacentes (4-conectadas)
- Peso = distancia + penalty por diferencia de Y (saltos)
- Path precalculado HRP → coin, el collector sigue waypoints en
  lugar de ir en línea recta

Esto mataría los "wall-crosses visibles" y haría el movimiento lucir
natural aun sin HUMANIZED, siguiendo rutas por pasillos.

## Mapas capturados (2026-11-10, rotación estándar)

Fase 1 **corriendo en vivo**. 9 mapas en rotación capturados con
`map_recon.lua` (grid 6 studs, raycast down → walkable Y por celda).
Full walkable arrays persistidos en el workspace del executor como
`mm2-maps/<mapName>.json`. Resumen abajo + `mm2-maps/_summary.json`.

| Mapa | parts | walkable | bbox size | notas |
|------|-------|----------|-----------|-------|
| Farmhouse | 8512 | 4859 | 551 × 310 × 619 | zombies; **bug** piso/techo |
| Manor | 5418 | 1554 | 317 × 80 × 344 | haunted house clásico |
| Mansion2 | 2441 | 1554 | 249 × 83 × 227 | compact |
| VampireCastle | 5125 | 616 | 758 × 249 × 989 | bbox más grande |
| Spaceship | 6519 | 1370 | 294 × 87 × 343 | sci-fi |
| MilBase | 3014 | 3973 | 384 × 243 × 554 | outdoor |
| Mineshaft | 6099 | 801 | 126 × 310 × 340 | vertical / underground |
| Bank2 | 3663 | 253 | 53 × 117 × 135 | bbox más chico |
| ResearchFacility | 4200 | 497 | 248 × 43 × 160 | un solo piso |

**Total: 9 mapas** (operador estimó 8-10 — dentro de rango).

Pendiente: event maps de Halloween 2026 si hay rotación especial aún
activa; se capturarán automáticamente si aparecen.

## Archivos relacionados

- [[mm2-scripts]] — scripts base del farmer
- [[changelog]] — versiones del collector
- `scripts/mm2-candy-farm/collector.lua` — consumidor del pathfinder

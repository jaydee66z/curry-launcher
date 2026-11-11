# Advanced — Luau executor fallback

> Si el Rakbot puro falla, caer de nuevo al Luau executor es la opción confiable.

## Executors recomendados (noviembre 2026)

| Executor | Precio | Nota |
|----------|--------|------|
| **Synapse X** | ~$20/mes | Gold standard, siempre update |
| **Krnl** | Gratis | Buen performance, key system |
| **Script-Ware** | ~$18/mes | Alternative, similar a Synapse |
| **AWP (Accurate Web Proxy)** | Gratis | Nuevo, aún estabilizando |
| **Delta Executor** | Gratis | Mobile-focused, PC via emulator |
| **Fluxus** | Gratis | Popular, key diario |
| **Hydrogen** | Gratis (Android) | Android-only |

Para scale pequeño (5-10 cuentas) en 1 PC: **Krnl** o **Fluxus** gratis es suficiente.

Para produccion stable: **Synapse X** vale los $20.

## Multi-instance Roblox

Roblox no deja abrir 2 clientes por default. Fix:

### Windows — MultiRBLX

Patcher que permite abrir N instancias:
- Download de un repo público (search "Multi Roblox Launcher")
- Correr antes de abrir Roblox
- Cada click launcher abre instance separada

### Shell workaround

```batch
@echo off
start "" "C:\Users\...\RobloxPlayerBeta.exe"
timeout 1
start "" "C:\Users\...\RobloxPlayerBeta.exe"
timeout 1
start "" "C:\Users\...\RobloxPlayerBeta.exe"
```

Esto abre 3 instancias. Cada una loguea su propia cuenta.

## Workflow 5-10 cuentas con Luau

1. Multi-instance patch → abre 10 Roblox
2. Logear cuenta diferente en cada uno
3. Entrar a MM2 (place ID link o buscar en catalog)
4. Abrir executor (Synapse/Krnl) → attach al proceso Roblox
5. Cargar `Main.luau` → Execute
6. Repetir para cada ventana

## Automatización semi-manual

Script AutoHotkey que:
- Lanza 10 instancias Roblox
- Espera join de cada una
- Attacha executor + fire Execute

Esto ahorra el "repetir para cada ventana" tedioso.

```autohotkey
; AutoHotkey script — pseudocode
Loop, 10 {
    Run, "C:\Path\RobloxPlayerBeta.exe"
    Sleep, 5000
    ; Luego abrir Synapse y autoinject
}
```

Hay repos en GitHub con AHK scripts for this.

## RAM / CPU por instancia

1 Roblox + 1 executor ≈ 400-800 MB RAM. Para 10 instancias: **4-8 GB RAM minimum**.

Si tu PC es 16 GB → 10 instancias cómodamente. 32 GB → hasta 20.

CPU: 1 core por 3-4 instancias (Roblox es single-threaded mostly).

## Limitaciones vs Rakbot puro

| Factor | Luau executor | Rakbot puro |
|--------|---------------|-------------|
| Max instancias | ~10 por PC | ~500 por VPS |
| Costo infra | $0 | $30-100/mes |
| Executor fee | $0-20/mes | $0 |
| Deploy complexity | Low | Medium |
| AC risk | Medium (Hyperion anti-exec) | Medium (payload detection) |
| Resilience | Low (1 crash PC → todo down) | High (distribuido) |

## Hybrid architecture

Mejor de ambos:
- **Rakbot puro VPS**: 500 cuentas heavy farmers
- **Luau executor en tu PC**: 5-10 cuentas "premium" con mother accounts (trading, high-value)

Rakbot escala, Luau manages the sensitive ones.

## Setup Luau rollback rápido

Si el port Python falla, para activar Luau en <30 min:

1. Instalar Synapse X (o Krnl free)
2. Instalar multi-instance patch
3. `git checkout mm2-0.49` en repo (confirma Main.luau estable)
4. Lanzar Roblox × 5-10, logear cuentas
5. Attach executor, cargar `scripts/mm2-candy-farm/Main.luau`
6. Execute → farm empieza

Total: 20-30 min + $0-20 executor.

## Automation al nivel GUI

Si querés escalar Luau a 30+ cuentas:
- Dedicated gaming VPS (dedicated GPU, Windows-based) 
- Cost ~$100-200/mes para GPU VPS
- Corre Roblox + 20-30 instancias
- Automatización con AHK/PyAutoGUI

Pero esto ya pierde la ventaja de "costo bajo". Si vas a pagar >$100/mes, mejor doble en Rakbot puro con 2 VPS CX42.

## Links

- [[../mm2-port/06-rollback-plan]]
- [[../infrastructure/00-overview]]

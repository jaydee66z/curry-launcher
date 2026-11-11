# Developer — code style

> Convenciones mínimas para que el código sea mantenible.

## Python

### Formatting

- Line length: **100 chars** (not 80)
- Indent: **4 spaces** (no tabs)
- Blank lines: 2 entre top-level defs, 1 entre methods
- String quotes: `"double"` por default, `'single'` para keys/short literals

### Naming

- `snake_case` para funciones + variables
- `PascalCase` para classes
- `SCREAMING_SNAKE` para constants
- `_leading_underscore` para "private" (convention, not enforced)

### Imports

```python
# stdlib
import math
import sys
from pathlib import Path

# third-party
import requests
import unittest

# local project
from rakbot.bootstrap import Credential
from rakbot import mm2_wire
```

Separados por línea vacía. Ordenados alfabético dentro cada grupo.

### Type hints

Usar donde agregan claridad:

```python
def get_coin(inspector: "Inspector", coin_key: tuple) -> bytes | None:
    ...
```

**No** usar para todo (noise):
```python
# Overkill:
def add(a: int, b: int) -> int:
    return a + b
```

### Docstrings

- Módulos: 1-line al top:
  ```python
  """MM2 farm session — discovery + pickup via GetCoin remote."""
  ```
- Funciones públicas: `"""short one-liner."""` o longer si necesita explicación
- Private helpers: optional

### Errors

```python
# NUNCA
assert len(data) > 0, "data vacío"

# YES
if not data:
    raise ValueError("data must be non-empty")
```

Rakbot usa custom exceptions: `BootstrapError`, `CryptoError`, `RateLimited`, `NetworkUnavailable`, etc. Raise las apropiadas.

### Pcall-equivalent

```python
# Para "do this but don't crash if fails"
try:
    risky_thing()
except Exception as e:
    emit({"event": "risky_err", "msg": str(e)[:160]})
```

Capturar TODO es anti-pattern — captá solo lo específico que podés handle. Pero en loops críticos (heartbeat, main loop), capturar `Exception` general es ok para no morir.

### Logging vs emit

- `print()` — minimal usage, debugging only
- `warnings.warn(...)` — para condición rara pero no error
- `emit({"event": "...", ...})` — para JSON lines a stdout (mass_worker pattern)
- `raise` — para errores que deben propagar

## Luau

### Naming

- `camelCase` para functions + variables (convención Roblox)
- `PascalCase` para classes/singletons
- `SCREAMING_SNAKE` para constants (mi preferencia)

### Scope

Declarar `local` SIEMPRE:
```lua
local count = 0           -- ✅
count = 0                 -- ❌ pollutes globals
```

Excepción: `_G.farmDebug` intencional para cross-script communication.

### Modules

```lua
-- scripts/mm2-candy-farm/my_module.lua
local module = {}

function module.doThing(x)
    return x * 2
end

return module
```

Cargar con:
```lua
local my = require(path)
my.doThing(5)
```

### Comments

- `--` para single-line
- `--[[  ]]` para block. Headers de versión usan block con `=====`
- Explicar POR QUÉ, no QUÉ. El código ya dice qué.

```lua
-- v0.44: hover BV is created at CharacterAdded (not lazily in heartbeat)
-- because operator reported falling-through-floor at round start when
-- lazy creation left a few frames with pure gravity.
local function onCharacter(char) ...
```

### Error handling

```lua
local ok, result = pcall(risky_function, arg1, arg2)
if not ok then
    warn("risky_function failed: " .. tostring(result))
    return nil
end
```

## Markdown (docs/)

### Structure

```markdown
# Título

> Opcional: 1-line summary / cuándo leer esto.

## Section

Prose o bullets.

### Subsection

- bullet
- bullet

```código```

| Tabla | con | columnas |
|-------|-----|----------|

## Links

- [[other-note]]
```

### Linking

Usar wikilinks `[[note-name]]` sin `.md`. Obsidian los resuelve.

Para subfolders: `[[subfolder/note-name]]`.

### Code blocks

Siempre con language hint:
```python
def foo(): pass
```

```bash
cd ...
```

### Emojis

Usar sparingly para énfasis visual:
- ✅ para listas de tareas completas
- ❌ para features NOT implementadas
- ⚠️ para warnings críticos
- 🚨 para alertas urgentes
- 🔒 para security topics

**No** usar en código commiteado (unless específicamente pedido).

## Git

### Commit messages

```
<type>: <subject>

<body explaining why, 72 chars per line>

<optional co-author>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`.

Ejemplo:
```
fix: hover BV at CharacterAdded prevents round-start fall

Operator reported falling through floor every round start. Root
cause: hover BV was created inside heartbeat the first time
wasFarming engaged. During the 2s START_DELAY, the character had
no vertical hold -> gravity pulled it below map.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

### Branches

- `main` — estable
- `dev` — integration (default working branch)
- `feature/<name>` — per feature
- `fix/<slug>` — per bug

### Tags

Semver-ish for releases:
- `mm2-0.X` — Luau script releases
- `mm2-py-0.X` — Python port releases
- `v0.X.Y` — major project versions

### Push convenciones

```bash
git push origin dev          # usually
git push origin dev --tags   # when tagging
git push --force             # NEVER (rewrite history dangerous)
```

## Links

- [[00-contributing]]
- [[02-testing-strategy]]

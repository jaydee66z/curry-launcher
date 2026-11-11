# Developer — contributing guide

> Si contratás un dev para que extienda este proyecto, pasale esto.

## Setup

```bash
git clone https://github.com/jaydee66z/curry-launcher.git
cd curry-launcher
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# o: .venv\Scripts\activate  (Windows)
pip install -U pip
pip install -r requirements.txt

# Verificar
python -m unittest discover -s rakbot/tests -v
# Debería mostrar "Ran 28+ tests in X.Xs / OK"
```

## Branching

- `main` — estable, mergeos via PR
- `dev` — integración (por default trabajamos acá)
- `feature/<name>` — tu branch
- `fix/<slug>` — para bugs específicos

Workflow:
```bash
git checkout dev
git pull
git checkout -b feature/mi-cambio
# ... código ...
git add <files>
git commit -m "feat: descripción corta"
git push origin feature/mi-cambio
# Abrir PR a dev
```

## Convenciones de código

### Python

- **Target**: Python 3.12+ (usamos `compression.zstd`, union types)
- **Style**: PEP 8 + 100 char line length
- **Imports**: stdlib → external → local rakbot
- **Docstrings**: 1-line summary en cada módulo + cada public function
- **Type hints**: donde agregan claridad (no obsesionar)
- **Errors**: NUNCA `assert` para runtime checks → raise exception propia
- **Secrets**: NUNCA en código → env vars o archivos gitignored

### Luau

- **Version**: Roblox Luau (no stock Lua 5.1)
- **Primitivas**: `task.wait`, `task.spawn`, `continue`, `typeof`
- **Nunca**: `loadstring` en código commiteado, `getrawmetatable` sin razón

### Commits

Formato:
```
<tipo>: <summary corta>

<cuerpo explicando por qué, no qué>
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

## Tests

### Añadir tests para nuevo código

```python
# rakbot/tests/test_<module>.py
import unittest
from rakbot import my_module

class TestMyFeature(unittest.TestCase):
    def test_happy_path(self):
        result = my_module.do_thing("input")
        self.assertEqual(result, "expected")
    
    def test_error_case(self):
        with self.assertRaises(ValueError):
            my_module.do_thing(None)

if __name__ == '__main__':
    unittest.main()
```

Ideal: 1 test por función, +1 por edge case.

### Correr tests

```bash
python -m unittest discover -s rakbot/tests -v
```

Target: 100% pass rate SIEMPRE.

### Coverage (optional)

```bash
pip install coverage
coverage run -m unittest discover -s rakbot/tests
coverage report
```

Target: >70% coverage en código nuevo.

## Documentar nuevos features

Cada feature nueva → mínimo 1 doc en `docs/obsidian/`:

- Si touches wire protocol → `mm2-port/02-wire-protocol.md`
- Si agregás nuevo juego → `rakbot-deep-dive/07-adding-new-game.md` ← actualizar + crear `<game>-port/00-status.md`
- Si fix bug recurrente → `troubleshooting/XX-<slug>.md`
- Si infrastructure change → `infrastructure/XX-...md`

## Secrets handling

**NUNCA** commitear:
- Cookies (`cookies.txt`, `*.live.txt`, etc)
- Proxy credentials (`proxies.txt`, `proxies.local.*`)
- Webhook URLs (`webhook.local.lua`)
- Passwords, API keys, tokens

Verificar ANTES de cada commit:
```bash
git diff --cached | grep -iE "(roblox|cookie|password|webhook)" && echo "⚠️ SECRET IN DIFF — ABORT"
```

Agregar al `.gitignore` NUEVOS archivos sensibles ANTES de crearlos.

## Code review checklist

Antes de aprobar un PR, verificar:

- [ ] Tests nuevos agregados para código nuevo
- [ ] Tests existentes siguen pasando
- [ ] Docstrings en funciones públicas
- [ ] Sin `print()` dejados por debug (usar `emit()` o `warnings`)
- [ ] Sin secretos en diff
- [ ] Documentation actualizada si aplicable
- [ ] Changelog entry (si cambio notorio)

## Deployment

Tras merge a `dev`:
1. Opcional: `git tag mm2-py-0.X`
2. Push tags: `git push origin dev --tags`
3. Deploy a VPS:
   ```bash
   ssh farmbot@VPS
   cd curry-launcher
   git pull origin dev
   sudo systemctl restart mm2farm
   ```
4. Monitorear logs 10 min para confirmar no regression

## Debugging

Ver [[../advanced/01-udp-debugging]] para UDP packets.
Ver [[../troubleshooting/00-index]] para bugs comunes.

## Contact

Owner: Eduardo (`jaydee66z`)
Collaborator: `permusulol`

## Links

- [[MOC]]
- [[01-code-style]]
- [[02-testing-strategy]]

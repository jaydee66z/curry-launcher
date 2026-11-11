# Developer — testing strategy

> Qué testear, cuándo, y cómo.

## Pyramid

```
                   /\
                  /  \      E2E tests (live)
                 /    \     — manual + staging
                /======\
               /        \   Integration tests
              /          \  — multi-module
             /============\
            /              \
           /    Unit tests   \  ← MAYORÍA
          /    (90% of tests)  \
         ========================
```

## Unit tests

**Scope**: una función o clase pequeña, aislada.

**No tocan**: network, filesystem, Roblox, time (use mocks/fakes).

**Target**: cada public function en `rakbot/mm2_*.py` y `rakbot/proxy_pool.py`.

Ejemplo (actual):
```python
# rakbot/tests/test_mm2_wire.py
def test_variant_string_shape(self):
    out = mm2_wire.variant_string("Halloween2026Box")
    self.assertEqual(out[:1], b'\x02')
    self.assertEqual(out[1:], string("Halloween2026Box"))
```

**Cuándo escribirlos**: ANTES o DURING coding (TDD). Depués es más work.

### Fixtures

Usar `@dataclass` o fakes simples en vez de mocks heavy. Ejemplo (actual):

```python
class _NodeStore(dict):
    def children(self, parent_key):
        return [(k, n) for k, n in self.items() if n.get('parent') == parent_key]

class _FakeInspector:
    nodes = _NodeStore()
    schema = _Schema()
    own = (99, 1)
```

Ejecuta rápido, legible, no depende de Rakbot internals.

## Integration tests

**Scope**: múltiples módulos interactuando.

**No tocan**: Roblox real.

Ejemplo:
```python
# rakbot/tests/test_mass_worker_integration.py
def test_worker_with_fake_bootstrap():
    # Create a real mass_worker.run() call but mock bootstrap + GameClient
    with patch('rakbot.mass_worker.RobloxBootstrap') as MockBS:
        mock_bs = MockBS.return_value
        mock_bs.authenticate.return_value = Account(user_id=12345, username='test')
        mock_bs.prepare.return_value = fake_connection_info()
        
        with patch('rakbot.mass_worker.GameClient') as MockGC:
            mock_gc = MockGC.return_value
            mock_gc.inspector = _FakeInspector()
            mock_gc.transport = _FakeTransport()
            
            # Pretend stdin has cookie
            with patch('sys.stdin.readline', return_value='{"cookie":"_|...xyz"}'):
                result = mass_worker.run(args_with_mm2=True)
                self.assertEqual(result, 0)
```

**No implementado todavía** — blueprint para futuro.

## E2E tests (live)

**Scope**: todo el stack contra Roblox real.

**Tocan**: Red, cookies, API Roblox.

**Caro** (puede banear cuentas). Correr solo pre-release.

Protocol:
1. Checkout latest `dev` branch
2. Load UN cookie dedicado para testing (no producción)
3. Correr: `python -m rakbot.mass_worker --mm2 --mm2-dry-run ...`
4. Verificar: logs muestran `dry_send` events sin crashes
5. Luego live: `python -m rakbot.mass_worker --mm2 ...` (sin dry-run)
6. Verificar: `pickup` events llegan después de 1-2 min

**Resultado test**: PASS/FAIL con criterios claros.

## Regression tests

Cada bug que arreglás → test para asegurar no vuelve.

Ejemplo:
```python
# test_mm2_wire.py agregado para bug v0.40
def test_no_goto_crash(self):
    """Regression: v0.40 bug donde goto skip_coin crashe silent.
    Replaced with if/else flag."""
    # Build scenario que before crasheaba
    insp = _Inspector()
    # No coins — should NOT raise
    best = mm2_wire.find_remote(insp, ("missing",), class_name="RemoteEvent")
    self.assertEqual(best, (None, None))
```

Nombre del test referencia el bug: `test_no_<bug_description>`.

## Mutation testing (advanced)

Herramienta: `mutmut`. 

```bash
pip install mutmut
mutmut run --paths-to-mutate rakbot/mm2_wire.py
mutmut results
```

Produce "mutants" (changes a tu código) y verifica qué tests siguen pasando. Si cambia una línea Y los tests siguen PASANDO → ese test NO cubre esa línea.

Target coverage: >90% killed mutants.

**Opcional** — para proyectos críticos. No urgent para MM2 farm.

## Performance / load tests

Para scale a 1000 cuentas, verificar que no hay regresiones de performance:

```python
# rakbot/tests/test_performance.py
import time
def test_tick_under_10ms(self):
    insp = _large_inspector(5000 nodes)
    session = Session(insp, transport, ...)
    # Prime
    session.tick()
    # Measure
    t0 = time.monotonic()
    for _ in range(100):
        session.tick()
    elapsed = time.monotonic() - t0
    # 100 ticks / N ms = (elapsed * 1000 / 100) ms each
    self.assertLess(elapsed * 10, 10, "Each tick must be <10ms")
```

Si algún cambio hace tick lento → caught en test.

## CI (continuous integration)

Setup básico con GitHub Actions:

```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python -m unittest discover -s rakbot/tests -v
```

Cada push a `dev` → corre tests → notificá via Discord si FAIL.

## Testing checklist antes de merge a `main`

- [ ] Todos los tests pasan localmente
- [ ] CI verde
- [ ] Cambios cubren con tests nuevos
- [ ] Documentation actualizada
- [ ] CHANGELOG actualizado
- [ ] Rollback plan documentado si breaking change

## Links

- [[00-contributing]]
- [[../mm2-port/05-testing-plan]]

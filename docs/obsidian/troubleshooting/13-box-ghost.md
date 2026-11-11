# Troubleshooting — box se cuenta pero no aparece item

## Síntoma

Logs muestran `{"event": "box_fired", "boxes_opened": N}` pero:
- Inventory (Weapons.Owned) no incrementa
- `read_candies` no cambia (-600 esperado pero sigue igual)

## Causas

### 1. OpenCrate falló server-side pero bot asumió success

El bot mira si `_safe_send(payload)` devuelve True (que sólo chequea que `transport.send` no excepcionó). NO verifica que el server realmente procesó el OpenCrate.

Resultado: cuenta de `boxes_opened` sube pero realmente nada pasó.

**Fix**: después de fire, verificar `read_candies` cayó por 600:

```python
# mm2_client._maybe_open_box:
before = candies
if self._safe_send(payload):
    # Esperar 500ms + verificar
    time.sleep(0.5)
    after = mm2_inventory.read_candies(self.inspector)
    if after is not None and (before - after) >= BOX_THRESHOLD:
        self.boxes_opened += 1
        self.emit({"event": "box_opened", ...})
    else:
        self.emit({"event": "box_failed", "before": before, "after": after})
        # Mark cookie as problematic?
```

### 2. Server respondió success pero item en "pending claim"

Algunos juegos ponen items en "pending claim" (aparecen en inventory solo después de leer un prompt).

MM2 no debería tener este flow para boxes — pero verificar.

### 3. ProfileData.Weapons.Owned no se replica

Si por alguna razón ProfileData subtree no se replica al cliente, `snapshot_owned_weapons` devuelve vacío/stale. El watcher nunca ve nuevos items.

**Diagnóstico**:
```python
from rakbot.mm2_inventory import snapshot_owned_weapons, _find_profile_data_table
root = _find_profile_data_table(inspector)
print(f"profile_data_key: {root}")
print(f"owned weapons: {snapshot_owned_weapons(inspector)}")
```

Si root es `None` → ProfileData no está en el replicated world. Fix: investigar schema change.

### 4. Server devuelve `false` sin consumir candies

OpenCrate devuelve `false` cuando:
- Shop UI no está active (?)
- Currency mismatch
- Server-side error

El bot asume que si no hay error, funcionó. Chequear return value.

Como RemoteFunction, `InvokeServer` devuelve el result. Rakbot necesita ESCUCHAR la response en la NEXT Event packet. Esto es más complejo que fire-and-forget.

Workaround: aceptar false positives y usar el "candy diff" como verificador.

## Fix robusto

Agregar `box_verifier` que confirme post-send:

```python
# mm2_client.py
def _maybe_open_box(self):
    candies_before = mm2_inventory.read_candies(self.inspector)
    if candies_before is None or candies_before < BOX_THRESHOLD:
        return
    payload = mm2_wire.opencrate_payload(self.inspector, self.next_invocation_id)
    if payload is None:
        return
    self.next_invocation_id += 1
    sent = self._safe_send(payload)
    if not sent:
        return
    # Verify by polling candies for next 3s
    for _ in range(6):
        time.sleep(0.5)
        candies_after = mm2_inventory.read_candies(self.inspector)
        if candies_after is not None and candies_before - candies_after >= BOX_THRESHOLD:
            self.boxes_opened += 1
            self.emit({"event": "box_confirmed", 
                       "boxes": self.boxes_opened,
                       "before": candies_before,
                       "after": candies_after})
            return
    # Timeout: no decrement. Log + continue
    self.emit({"event": "box_timeout", 
               "before": candies_before, 
               "last_after": candies_after})
```

Esto garantiza que el `boxes_opened` counter refleja REALLY opened boxes.

## Diagnóstico extra

### Re-run con dry-run

```bash
# Verificar que el payload de opencrate es correcto
echo '{"cookie": "..."}' | python -m rakbot.mass_worker --mm2 --mm2-dry-run --place-id 142823291 --duration 120
```

Si ves `dry_send` events con bytes que empiezan con `0x83 0x07` → payload format OK.

Si NO ves ningún `dry_send` para opencrate → la lógica `_maybe_open_box` nunca dispara. Verificar:
- `read_candies` devuelve >= 600?
- `BOX_THRESHOLD` setting correcto?
- Enough time passed since last check (3s interval)?

### Capture Luau Main.luau behavior

Correr Main.luau en executor; cuando abra box, log exactamente los args de `OpenCrate:InvokeServer(...)`. Comparar con lo que Python emite.

Si Luau pasa 3 args `("Halloween2026Box", "MysteryBox", "Candies2026")` → matches. Sino → fix.

## Alternative: usar box_opener.lua standalone

Si el port Python no acepta OpenCrate, dejar Luau executor dedicated para box opening:

- Mother accounts corren Main.luau (Luau executor) para farm + open
- Farmer accounts (1000 Python) solo juntan candies sin abrir

Mother account opens boxes en bulk cada noche.

## Links

- [[00-index]]
- [[../mm2-port/02-wire-protocol]]
- [[../api-reference/02-mm2-remotes]]

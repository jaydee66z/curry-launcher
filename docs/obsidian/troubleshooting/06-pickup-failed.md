# Troubleshooting — payloads enviados pero candies no se cuentan

## Síntoma

En logs:
```json
{"event": "mm2", "dry_send": {"bytes": 23, "head": "830701..."}}
// ... many dry_send ...
{"event": "mm2", "candies_this_round": 0}  // never increments
```

O después de cambiar a live mode (sin dry_run):
- `transport.send` no da error
- Ningún `pickup` event aparece
- `lifetime_candies` sigue en 0

## Hipótesis ordenadas por probabilidad

### Hip. 1 — server rechaza silente por distancia

Nuestro payload es correcto pero HRP está fuera del radius que el server acepta.

**Verificar**: log HRP position + coin position:
```python
# agregar en mm2_client.Session._fire_coin:
coin = self.inspector.nodes[coin_key]
hrp = _hrp_position(self.inspector)
dist = _distance(coin['props'].get('CFrame', {}).get('position', (0,0,0)), hrp or (0,0,0))
self.emit({"event": "fire_debug", "coin": coin_key, "hrp": hrp, "dist": dist})
```

Si `dist > 10` → probablemente el server lo rechaza. Necesitás phase 2 (movement).

### Hip. 2 — payload byte-wrong

Nuestros opcodes están bien en teoría pero schema real difiere.

**Verificar**: ver [[02-schema-mismatch]] — habilitar diagnóstico de schema en `find_remote`.

### Hip. 3 — remote path mal

`ReplicatedStorage.Remotes.Gameplay.GetCoin` puede no existir en el schema (Nikilis renombra items evento a evento).

**Verificar**: dumpear paths de todos los RemoteEvents:
```python
# temporary addition in mass_worker.run_mm2_farm:
for key, node in inspector.nodes.items():
    if node['class'] == 'RemoteEvent':
        path = _path(inspector, key)  # from mm2_wire
        emit('remote_found', path=[p.decode('utf-8', 'ignore') for p in path])
```

Si el output NO contiene `('ReplicatedStorage', 'Remotes', 'Gameplay', 'GetCoin')` → el path cambió. Fix: actualizar `REMOTE_GETCOIN_PATH` en `mm2_wire.py`.

### Hip. 4 — inspector.own no apunta al player correcto

Si `inspector.own` es `None` o apunta a otro Player, `wire_guid(inspector.own)` en el payload incluye la ref incorrecta.

**Verificar**:
```python
own_node = inspector.nodes.get(inspector.own)
emit('own_debug', own=inspector.own, user_id=own_node['props'].get('UserId') if own_node else None)
```

Debería devolver `user_id == bootstrap.account.user_id`.

### Hip. 5 — coin.Collected attribute replicated with delay

El server marca Collected pero no replica hasta 500-1500ms después. Nuestro loop @ 20Hz re-fire al mismo coin → después de 2 fires → marca `visited` → nunca más fire.

**Verificar**: bumping `CONFIRM_TIMEOUT` a 2.0s:
```python
CONFIRM_TIMEOUT = 2.0  # was 0.6
```

Si funciona → el server tenía latencia alta, no el payload.

### Hip. 6 — coin ya está en visited de un run anterior

Si `visited` persiste entre rounds por bug → nunca pickeamos.

**Verificar**: `session.on_coins_started()` debería clearear. Logging:
```python
def on_coins_started(self):
    self.emit({"event": "round_start", "visited_before_clear": len(self.visited)})
    # ... rest
```

Después de 1 ronda completa: `visited` debería ser > 0, luego al inicio de la siguiente: `visited_before_clear > 0` (confirmando que clear fue llamado).

### Hip. 7 — CoinCollected event handler no triggered

Nuestro `_wrapped_event` en `mass_worker.run_mm2_farm` intercepta `inspector.event_value`. Si el nombre del event no matchea exactamente `'RemoteEvent.OnClientEvent'`, no cuenta pickups.

**Verificar**: dumpear TODOS los events en vivo:
```python
_orig = inspector.event_value
def spy(name, key, args):
    emit('any_event', name=name, args_count=len(args))
    _orig(name, key, args)
inspector.event_value = spy
```

Despues de 1-2 min: ver qué `name` values aparecen. Si ves `'RemoteEvent.OnClientEvent'` después de un fire exitoso → el handler funciona. Si no, buscar el name real y adaptar.

## Diagnóstico combinado

Agregar hooks a `mm2_client.Session`:

```python
# En Session.__init__ agregar:
self._fire_count = 0
self._last_fire_time = 0

# En _fire_coin tras enviar:
self._fire_count += 1
self._last_fire_time = time.monotonic()
self.emit({"event": "fire_debug", "count": self._fire_count,
           "coin_dist": dist, "hrp": hrp})

# Cada 60s en run():
if time.monotonic() - self._last_report > 60:
    self.emit({"event": "60s_report",
               "fires": self._fire_count,
               "pickups": self.candies_this_round,
               "visited_coins": len(self.visited)})
    self._last_report = time.monotonic()
```

Después de 5 min, el ratio `pickups/fires` te dice qué pct de fires funcionan.

## Si NADA funciona (phase 1 falló)

Vía dos opciones:

### A. Capturar un fire real de Luau

Con Main.luau corriendo en executor y Rakbot separately autenticado, usar `remote-spy` del `roblox-mcp` para capturar el payload UDP que Luau manda al server. Compararlo byte a byte con lo que Python emite.

Si matchean → bug está en el transport (Python no manda bytes correctos al server). Debug en `persistent_client.py`.

Si NO matchean → bug está en los encoders. Ajustar `mm2_wire.py`.

### B. Fallback: hybrid architecture

- Rakbot maneja auth + join + CoinCollected event listening
- Un Main.luau standalone en executor hace fire (limitación: 1 PC max 10 cuentas)

Pero esto NO escala a 1000 → eventually hay que fix phase 1 port.

## Links

- [[00-index]]
- [[02-schema-mismatch]]
- [[../mm2-port/02-wire-protocol]]
- [[../mm2-port/04-navigation-roadmap]]

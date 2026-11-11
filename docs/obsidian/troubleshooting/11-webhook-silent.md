# Troubleshooting — Discord webhook silent

## Síntoma

No llegan embeds a tu canal Discord aunque:
- Logs del bot muestran `event: rare_drop`
- Logs muestran `event: box_fired`
- Pero NO hay post en el canal

## Causa 1 — URL incorrecta

```bash
echo $MM2_DISCORD_WEBHOOK_URL
```

Esperado:
```
https://discord.com/api/webhooks/1234567890/abcdefghijk...
```

Si vacío / malformado → el watcher skip con `warn("WEBHOOK_URL not set")`.

Fix:
```bash
export MM2_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/TU_ID/TU_TOKEN"
# Agregar a ~/.bashrc para persistir
echo 'export MM2_DISCORD_WEBHOOK_URL="..."' >> ~/.bashrc
```

Restart subprocess para que lea la variable:
```bash
sudo systemctl restart mm2farm
```

## Causa 2 — webhook deleted o expirado

En Discord:
- Server settings → Integrations → Webhooks
- Si tu webhook aparece con "Disabled" o directly missing → fue borrado

Fix: crear uno nuevo:
- Server → Settings → Integrations → New Webhook
- Elegir canal
- Copy URL
- Update `MM2_DISCORD_WEBHOOK_URL`

## Causa 3 — rate limit Discord

Discord permite ~30 messages/min por webhook. Si spamás alerts → 429 → silent drop.

Verificar:
```bash
curl -v -X POST "$MM2_DISCORD_WEBHOOK_URL" -H "Content-Type: application/json" -d '{"content":"test"}'
```

Si returns 429 → rate limited. Wait 5-10 min.

Fix: throttle alerts en el bot:
```python
# rakbot/mm2_inventory.py EmbersickleWatcher
self._last_send = 0
MIN_INTERVAL = 2.0  # seconds between posts

def _send(self, item_key, variant):
    now = time.time()
    if now - self._last_send < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - (now - self._last_send))
    # ... rest
    self._last_send = time.time()
```

## Causa 4 — DataImpulse proxy en webhook request

Si el POST a Discord pasa por DataImpulse proxy → DI puede dropearlo (no es Roblox traffic).

Verificar: `urllib.request.urlopen(req)` en `mm2_inventory.py` **NO debería** usar ProxyHandler.

Fix: asegurar que el webhook usa `urllib` crudo sin opener con proxy:

```python
import urllib.request

def _send(self, item_key, variant):
    req = urllib.request.Request(self.webhook_url, ...)
    # NO: opener = urllib.request.build_opener(ProxyHandler(...))
    # YES:
    with urllib.request.urlopen(req, timeout=5) as resp:  # uses default opener
        ...
```

Default opener no usa proxy → va direct a Discord.

## Causa 5 — HTTPS cert error

Si VPS tiene cert bundle desactualizado:

```
urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED]>
```

Fix:
```bash
sudo apt install ca-certificates
sudo update-ca-certificates
```

O workaround (menos seguro):
```python
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
    ...
```

Solo usar si realmente no podés instalar certs.

## Causa 6 — body JSON malformado

Si el embed JSON tiene caracteres que Discord rejects:
- Emojis en campos string: ok generally
- Null en field required: 400
- Length too big (title >256 chars, description >4096): 400

Verificar: hacer dry-run manual con el body:

```bash
curl -v -X POST "$MM2_DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"username":"Test","embeds":[{"title":"Test","description":"Test body","color":15844367}]}'
```

Si 200 → body es OK. Si 400 → body rejected, revisar JSON exact.

## Causa 7 — channel permissions

Si el canal destino de webhook está locked / archived:
- Webhook sigue "existing" pero posts fail silently
- Diagnóstico: cambiar webhook a otro canal y probar

## Verificar que watcher corre

```bash
# Logs: ¿hay evidence del thread spawn?
grep "EmbersickleWatcher\|rare_drop\|webhook" logs/mm2farm.log | tail -20
```

Debería haber:
```
[farm/inv] baseline captured (N owned items)
```

Si NO → el watcher nunca arrancó. Causa probable: `inspector.own` no estaba disponible al arranque → `EmbersickleWatcher` falló silent.

Fix: verificar en `mass_worker.run_mm2_farm`:
```python
watcher = EmbersickleWatcher(inspector, username=account.username or '', ...)
watcher.start()   # <-- debe llamarse
```

## Test end-to-end

```python
# En Python REPL:
from rakbot.mm2_inventory import EmbersickleWatcher

# Create dummy inspector + watcher
class DummyI:
    nodes = {}
    pass

w = EmbersickleWatcher(DummyI(), username='test', user_id=12345,
                       webhook_url='<TU URL>', emit=print)
w._send('Embersickle', 'common')

# Deberías ver un post en Discord
```

Si llega → el send funciona. Si no → URL/rate limit/cert.

## Links

- [[00-index]]
- [[../mm2-port/00-status]]
- [[../rakbot-deep-dive/00-overview]]

# API Reference — Rakbot public API

Métodos públicos expuestos por los módulos principales. Útil para scripting + extending.

## `rakbot.bootstrap`

### `Credential(value: str)`

Normaliza un `.ROBLOSECURITY` cookie. Acepta con o sin prefijo.

```python
cred = Credential("_|WARNING...<blob>")
cred.value  # el blob
```

### `RobloxHTTP(timeout=10, *, proxy_url=None)`

HTTP client con proxy opcional.

```python
http = RobloxHTTP(proxy_url="http://user:pass@gw.dataimpulse.com:10000")
reply = http.request(IDENTITY_URL, credential=cred)
# reply.status, reply.headers, reply.body
```

### `RobloxBootstrap(credential, *, http=None, account_id=None, proxy_pool=None)`

High-level auth + prepare.

```python
bs = RobloxBootstrap(cred, account_id=0, proxy_pool=pool)
account = bs.authenticate()  # Account(user_id, username, ...)
info = bs.prepare(142823291)  # ConnectionInfo for GameClient
```

### `read_mass_credentials(path, count)`

Loader de `cookies.txt`.

```python
from rakbot.mass import read_mass_credentials
creds = read_mass_credentials("cookies.txt", 9)
# Returns list of Credential
```

## `rakbot.proxy_pool`

### `ProxyPool(path=None)`

Carga proxies de `proxies.txt` o paths alternativos.

```python
pool = ProxyPool()               # auto-detect
pool = ProxyPool("my_proxies.txt")

pool.enabled()      # True si hay proxies loaded
pool.count()        # cantidad
pool.url_for(id)    # "http://user:pass@host:port" pinned a id
```

## `rakbot.replication`

### `Inspector(schema, user_id, *, max_nodes=65536)`

Decodifica packets Data.

```python
inspector = Inspector(schema, user_id)
inspector.push(packet_bytes)       # decode Data packet
inspector.push_isr(isr_bytes)      # decode ISR

# Overridable hooks
class MyInspector(Inspector):
    def property_value(self, key, name, value): ...
    def event_value(self, name, key, arguments): ...
    def removal_value(self, key): ...
    def instance_value(self, key, node): ...

# Attributes
inspector.nodes           # dict guid → {class, parent, props}
inspector.own             # guid del LocalPlayer
inspector.schema          # Schema obj
inspector.items           # Counter de items vistos
inspector.messages        # count de packets
```

## `rakbot.mm2_wire`

### `getcoin_payload(inspector, coin_key) -> bytes | None`

Encode un `GetCoin:FireServer(coin)`.

```python
payload = getcoin_payload(inspector, coin_key)
if payload:
    transport.send(payload)
```

### `opencrate_payload(inspector, invocation_id, box_id, type_name, currency) -> bytes | None`

Encode `OpenCrate:InvokeServer(box_id, type, currency)`.

```python
payload = opencrate_payload(inspector, invocation_id=1)  # defaults: Halloween2026Box, MysteryBox, Candies2026
```

### `find_remote(inspector, path, *, class_name) -> tuple[key, event_id] | (None, None)`

Resuelve path de un RemoteEvent/RemoteFunction.

```python
key, eid = find_remote(inspector, ("ReplicatedStorage", "Remotes", "Gameplay", "GetCoin"),
                       class_name="RemoteEvent")
```

### Variant encoders

```python
variant_instance(key)              # kind 28
variant_string("hello")            # kind 2
variant_array([v1, v2])            # wraps: varuint(n) + variants + 0x00
```

## `rakbot.mm2_client`

### `Session(inspector, transport, emit=print)`

Farm session per cuenta.

```python
session = Session(inspector, transport, emit=my_logger)

# Public API
session.tick()                     # one decision cycle
session.run(duration=3600, dry_run=False)  # blocking loop

# Hooks (called by caller when server events fire)
session.on_coins_started()
session.on_coin_collected(coin_type_bytes)

# State readable
session.candies_this_round
session.lifetime_candies
session.boxes_opened
```

## `rakbot.mm2_inventory`

### `read_candies(inspector) -> int | None`

Lee `ProfileData.Materials.Owned.Candies2026`.

### `snapshot_owned_weapons(inspector) -> set[str]`

Set de keys en `ProfileData.Weapons.Owned`.

### `EmbersickleWatcher(inspector, username, user_id, *, webhook_url=None, emit=print)`

Daemon thread que poll por drops.

```python
w = EmbersickleWatcher(inspector, "myname", 12345)
w.start()
# ...
w.stop()
```

## `rakbot.heli_wars`

### `wire_guid(key: tuple) -> bytes`

Serializa guid (scope, id) → bytes.

```python
wire_guid((5, 12345678))  # varuint(5) + struct.pack('<I', 12345678)
```

### `team_request(inspector, *, invocation_id=1) -> dict | None`

Builder completo del JoinTeam payload para Heli Wars. Útil como reference pattern.

## `rakbot.application`

### `varuint(n: int) -> bytes`

LEB128 encoder.

### `string(value: str) -> bytes`

`varuint(len) + utf8_bytes`.

### `protocol_sync(random_word=None) -> bytes`

Protocol sync packet (handshake).

## `rakbot.mass`

### `MassRunner(credentials, *, place_id, vip_link=None, mm2=False, mm2_dry_run=False, ...)`

Orchestrator de N subprocesses.

```python
runner = MassRunner(credentials, place_id=142823291, mm2=True, duration=3600)
runner.run()  # blocks until all done
```

### `read_mass_credentials(path, count) -> list[Credential]`

Ver arriba.

## `rakbot.mass_worker`

Normalmente invocado por `MassRunner`, no directo. Pero podés para debug:

```bash
echo '{"cookie": "..."}' | python -m rakbot.mass_worker --mm2 --place-id 142823291
```

Flags:
- `--place-id`
- `--attempts`
- `--duration`
- `--brainrot`
- `--only-best`
- `--mm2`
- `--mm2-dry-run`

## Links

- [[00-roblox-endpoints]]
- [[02-mm2-remotes]]
- [[../rakbot-deep-dive/00-overview]]

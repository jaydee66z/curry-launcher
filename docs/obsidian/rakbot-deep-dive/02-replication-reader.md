# Rakbot — replication reader

`rakbot/replication.py` lee los packets Data que el server envía al cliente. **NUNCA ejecuta Luau**, solo decodifica estructura.

## Clase `Inspector`

Estado:

```python
class Inspector:
    schema: Schema          # types + classes + events + properties
    user_id: int            # tu user id
    nodes: NodeStore        # dict guid → {class, parent, props}
    shared: set             # shared string hashes known
    own: tuple | None       # guid del Player owneado por el user_id
    items: Counter          # métricas de items vistos
    stops: Counter          # métricas de stops (errores)
    event_names: Counter    # qué remotes fired
    schema.events: list     # eventos conocidos de schema
    appearance_events: list # CharacterAppearanceLoaded events
    last_isr_frame: int     # último frame ISR visto
```

## Packet flow

```
server → UDP encrypted → decrypt (ChaCha20) → bytes with prefix 0x83 (Data)
                                                    │
                                                    ▼
                                    Inspector.push(packet) → reader walks items
                                                    │
                            ┌───────────────────────┼──────────────────────────┐
                            ▼                       ▼                           ▼
                       kind=0x02                kind=0x03                  kind=0x07
                       (NewInstance)          (ChangedProperty)             (Event)
                            │                       │                           │
                            ▼                       ▼                           ▼
                    new(reader)              changed(reader)             event(reader)
                            │                       │                           │
                            ▼                       ▼                           ▼
                   nodes[key] = {...}     nodes[key].props[name]=v    event_value(name,key,args)
                                                                        (user-overridable hook)
```

## Opcodes relevantes dentro de Data packets

| Opcode | Item | Función |
|--------|------|---------|
| `0x02` | NewInstance | Crea instance + sus props |
| `0x03` | ChangedProperty | Update de 1 property de 1 instance |
| `0x01` | Removal | Delete de 1 instance |
| `0x07` | **Event** | RemoteEvent fire (observable con `event_value`) |
| `0x16` | JoinData v2 | Inicial dump de world (zstd compressed) |
| `0x0d` | StreamData | Dump instances mid-game (streaming) |
| `0x1b` | DestroyInstance | Delete batch |
| `0x13` | AtomicReferences | 2 instance refs atomic |
| `0x14` | StreamRegionInfo | Region metadata |
| `0x15` | ChangedAttribute | Attribute change |
| `0x19` | Item:0x19 | 24 raw bytes (??) |
| `0x10`/`0x23` | Marker | u32 state value |
| `0x04` | Marker | 4 raw bytes |
| `0x05`/`0x06` | Ping | Ping request/response |
| `0x00` | Terminator | End of packet |

## Variant types (dentro de property values)

Cada property tiene un `type` del schema. Al decodificar, `Inspector.value(reader, type, ...)` switcha según el type number:

| Type | Encoding |
|------|----------|
| 2 | String — `varuint(len) + utf8` |
| 10 | ZigzagInt — `varuint((v<<1)^(v>>63))` |
| 12 | Double — `<d` (8 bytes little-endian) |
| 13 | ? — `<fi` (8 bytes) |
| 14 | ? — `<fifi` (16 bytes) |
| 19 | Vector3 — `<fff` (12 bytes) |
| 20 | Color3 — 3 raw bytes |
| 21 | Vector2 — `<ff` (8 bytes) |
| 27 | CFrame — 12 bytes pos + 1 byte rotation + optional 6 bytes |
| 28 | Instance ref — `wire_guid()` |
| 29 | VariantArray — `varuint(count) + variants + 0x00` |
| 30 | SameVariantArray — array of same type |
| 31 | Dictionary — `varuint(count) + (key, variant) pairs` |
| 33 | ContentId — ref to asset |
| 34 | UDim — `varuint(2^32-1)` |
| 35 | NumberSequence — skipped (count * 12 bytes) |
| 37 | UDim2 — `<ff` (8 bytes) |
| 38 | ColorSequence — skipped (count * 20) |
| 40 | NumberRange — `<ffff` (16 bytes) |
| 41 | Rect — 20-24 bytes |
| 46 | SharedString ref — 16 byte digest |
| 49 | OptimizedString — varuint-encoded with name cache |
| 51 | OptionalCFrame | similar to 27 but optional |
| 54 | Font | weight + style + 2 strings |
| 56 | Buffer | zstd compressed |
| 60 | DynamicResource | opaque |
| 61 | Content | opaque variant |
| 69 | Guid (via inspector.guid) | wire_guid() |

## Hooks que user puede overrider

```python
class MyInspector(Inspector):
    def property_value(self, key, name, value):
        # Called after each property update
        if name == "Health" and value <= 0:
            print(f"Node {key} died!")
    
    def event_value(self, name, key, arguments):
        # Called after each RemoteEvent OnClientEvent
        if name == "RemoteEvent.OnClientEvent":
            print(f"Event on {key}: {arguments}")
    
    def removal_value(self, key):
        # Called on instance deletion
        pass
    
    def instance_value(self, key, node):
        # Called after new instance committed to nodes
        pass
```

## Keeping properties (filtering)

Para grandes maps donde no querés retener TODO:

```python
class SlimInspector(Inspector):
    def keep_property(self, class_name, prop_name):
        if class_name == "Model" and prop_name in ("Attributes", "Tags"):
            return False  # skip these
        return True
```

Ahorra RAM pero perdés data. Default: retain all.

## Max nodes y eviction

Default `max_nodes=65536`. Si llegás al límite, el inspector evicta nodes marcados como "no important" (via `important_node()`). Tiene excepción para Players, Chat, Humanoid, HumanoidRootPart.

Si corrés 1000 cuentas con replicación a tope → cada subprocess tiene su Inspector → RAM total: 65k nodes × 1kb = 65 MB × 1000 = 65 GB. **Overprovisioned** — bajar `max_nodes=4096` para scale.

## Para MM2 farm específico

```python
class MM2Inspector(Inspector):
    def keep_property(self, class_name, prop_name):
        # Solo retenemos lo necesario para encontrar Coin_Server + HRP
        if class_name in ("Part", "MeshPart") and prop_name in ("Name", "CFrame", "Position"):
            return True
        if class_name == "Player" and prop_name in ("Character", "UserId", "Name"):
            return True
        if class_name in ("Humanoid",) and prop_name in ("Health", "WalkSpeed"):
            return True
        if class_name == "ModuleScript" and prop_name == "Name":
            return True  # para encontrar ProfileData
        if class_name in ("Folder", "ReplicatedStorage", "RemoteEvent", "RemoteFunction"):
            return True  # para path resolution
        return False
```

Esto reduce memoria y acelera scans. Usar en producción.

## Links

- [[00-overview]]
- [[01-bootstrap-flow]]
- [[03-persistent-client]]
- [[../mm2-port/02-wire-protocol]]

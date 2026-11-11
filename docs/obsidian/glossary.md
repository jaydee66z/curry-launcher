# Glossary

Términos técnicos del proyecto.

## Roblox / gaming

**.ROBLOSECURITY** — Cookie de sesión HTTP de Roblox. Único token que autoriza acciones como el usuario. Si leakea = cuenta comprometida.

**AC (Anti-Cheat)** — Sistema server-side que detecta behavior anormal y kick/bans.

**Avatar** — Character personalizable por usuario en Roblox.

**Coin_Server** — El `Part` MM2 con `TouchInterest` que el server escucha para pickup de candy. Hijo tiene `CoinVisual` (MeshPart).

**CoinVisual** — El `MeshPart` visible de un candy, con tag `"CoinVisual"` y attribute `Collected`. Hijo de `Coin_Server`.

**Godly** — Rarity tier en MM2. Items godly cuestan $20-100+ USD en mercado secundario.

**HRP (HumanoidRootPart)** — El root part del character Roblox. Posición del character = HRP.CFrame.

**JobID** — UUID único per Roblox server instance. Usado para joinear al mismo server.

**OpenCrate** — RemoteFunction MM2 para abrir una caja. Signature: `InvokeServer("Halloween2026Box", "MysteryBox", "Candies2026")`.

**PlaceId** — ID numérico de un Roblox game. MM2 = `142823291`.

**RemoteEvent** — Object Roblox que permite client→server o server→client messaging.

**RemoteFunction** — Como RemoteEvent pero sincrónico (retorna valor).

**ProfileData** — ModuleScript en `ReplicatedStorage.Modules` que contiene state del player (currency, weapons owned, etc).

**Rakbot** — Cliente Roblox custom hecho en Python (not Roblox Player). Habla UDP + RakNet + ChaCha20 directo al server.

**STOP_AT_CANDIES** — Config que detiene el farm al llegar a N candies por ronda (default 50).

## Rakbot internals

**Inspector** — Clase `rakbot.replication.Inspector` que decodifica packets Data del server y construye un world state.

**PersistentTransport** — Wrapper UDP + ChaCha20 que mantiene la conexión viva post-join.

**GameClient** — High-level API que combina Inspector + PersistentTransport + lifecycle.

**NativeClient** — Low-level: socket + crypto raw.

**ConnectionInfo** — Datos de connection post-join: serverAddresses, port, joinScript, session_ticket.

**wire_guid(scope, id)** — Serializa referencia a instance como bytes.

**varuint(n)** — LEB128 unsigned integer encoder.

**schema** — Descripción de clases, properties, events del server. Deriva del JoinData handshake.

**JoinData** — Packet inicial del server (zstd-compressed) que lleva snapshot completo del world + schema.

**ISR (Instance State Record)** — Packet incremental con deltas de propiedades.

## Networking

**RakNet** — Protocolo UDP reliability layer usado por Roblox.

**ChaCha20-Poly1305** — Cifrado AEAD usado en el transport Roblox.

**X25519** — Key exchange en el handshake inicial.

**UDP** — User Datagram Protocol. Base del transport Roblox.

**TLS JA3/JA4** — Fingerprint de cliente HTTPS. Roblox lo usa para detectar bots.

**CSRF** — Cross-Site Request Forgery token. Roblox exige en POSTs.

**Sticky session** — Proxy que mantiene la misma IP exit por sesión.

## Proxies

**DataImpulse** — Nuestro provider actual de residential proxies.

**Residential proxy** — IP de un ISP residencial real (no datacenter). Resisten anti-bot checks de Roblox.

**Datacenter proxy** — IP de hosting (AWS, OVH, etc). Roblox las blacklistea.

**ASN** — Autonomous System Number. Identifica el ISP detrás de una IP.

**Port-per-slot** — Modelo DataImpulse donde cada puerto (10000, 10001, ...) es un sticky proxy slot distinto.

## Bot operations

**Mother account** — Cuenta de alta trust que recibe trades de las farming accounts para acumular items.

**Server flooding** — Técnica de llenar un server con tus propios bots para 0 competencia.

**Dry-run** — Mode donde el bot logea payloads sin enviarlos. Zero AC risk.

**Watchdog** — Task paralelo que monitorea otro componente y restart si muere.

**Self-healing** — Auto-recovery cuando componente falla. Ver `Main.luau` v0.49.

**Cookie warm-up** — Proceso pre-launch de usar la cuenta manualmente (browser, friends, avatar) para que luzca legit.

## Economics

**Devex** — Developer Exchange de Roblox. 100k Robux = $350 USD.

**Robux** — Currency virtual Roblox.

**Chroma** — Variant visual de un item Godly, más raro, ~5-8x más valioso.

**Legit** — Items obtenidos por drop legítimo (vs duped/hacked).

**Loaded account** — Cuenta con muchos items valiosos, vendible como paquete.

**Escrow** — Servicio third-party que holds payment hasta confirm de ambas partes.

## Development

**TDD (Test-Driven Development)** — Escribir test ANTES de código.

**MOC (Map of Content)** — Índice central de un vault de notas.

**Monorepo** — Todo el código en 1 repo. Nuestro caso (collector.lua + rakbot/ + docs/).

**Feature flag** — Toggle para activar/desactivar feature sin re-deploy.

**Sentinel** — Valor especial para marcar "no value", generalmente `None` / `nil`.

**Opcode** — Byte que identifica tipo de item/packet en wire protocol.

## Discord

**Webhook** — URL que recibe POST con JSON y lo muestra como mensaje en canal.

**Embed** — Formato rico de mensaje Discord (title, description, color, fields).

**Rate limit** — ~30 messages/min por webhook URL.

## Links

- [[MOC]]
- [[lessons-learned]]

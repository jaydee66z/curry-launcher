# Rakbot — persistent client + transport

`rakbot/persistent_client.py` maintains la conexión UDP viva post-join. Encapsula la cripto, split TTL, retry budget.

## Clases

### `PersistentTransport`

El wrapper del socket UDP + ChaCha20 state.

```python
class PersistentTransport:
    def __init__(self, native_client, retry_budget=10):
        self.native = native_client
        self.retry_budget = retry_budget
        self._ack_pending = {}
        self._split_assembly = {}
    
    def send(self, payload: bytes):
        """Send one Data packet (or Event item, etc.) to server.
        Handles encryption + reliability layer transparently."""
    
    def recv(self, timeout=0.1):
        """Returns next decrypted packet or None if timeout."""
    
    def ping(self):
        """Keep-alive. Called periodically."""
    
    def disconnect(self):
        """Clean disconnect."""
```

El `send()` que usamos desde `mm2_wire.getcoin_payload` → `transport.send(payload)` debería mandar el packet exactamente como está, con el 0x83 header incluido.

**Verificar**: en `game_client.py` cómo se expone `transport`. Puede que el método no se llame `send` sino `send_data`, `send_packet`, `fire_remote` etc. Al despertar, leer `game_client.py` y adaptar.

### `NativeClient`

Más low-level: el socket + cripto raw. Expone:
- `encrypt(plaintext)` → ciphertext
- `decrypt(ciphertext)` → plaintext
- `send_raw(bytes)` → envía al socket
- `recv_raw(timeout)` → lee del socket

Normalmente NO tocar directamente.

## Reliability layer

Rakbot implementa RakNet reliability on top of UDP:
- **Ordered**: packets llegan en orden
- **Reliable**: retransmit si no ACK
- **Split**: packets grandes se fragmentan
- **Priority**: control vs data

Para fire remotes de MM2, usar **reliable ordered** (safest).

## Keepalive

Si no mandás nada en N segundos, Roblox desconecta. `PersistentTransport.ping()` envía un keepalive cada ~5s.

Nuestro `Session.tick()` corre @ 20Hz = hay traffic constante → nunca falta keepalive natural.

## Retry budget

Si un send() falla por network error, retry hasta `retry_budget` veces. Default 10. Después → raise `TransportDead`.

En `Session._fire_coin`:

```python
try:
    self.transport.send(payload)
except TransportDead:
    # network murió — señal para el subprocess de morir y let mass.py relaunch
    self.emit({"event": "transport_dead"})
    raise
```

## Encryption state

ChaCha20-Poly1305 con nonce que se incrementa por packet. El state se inicializa en `NativeOpen` durante el handshake. Si se pierde sync → disconnect.

## Logs útiles para debug

Si el transport muere, inspeccionar:
```python
transport.native._nonce_tx     # qué nonce TX estamos
transport.native._nonce_rx     # qué nonce RX esperamos
transport._ack_pending         # qué packets no acked
transport._retry_counter       # cuántos retries fallaron
```

## Patrones defensivos

### Pattern 1 — Send-and-forget

Para GetCoin/OpenCrate que son "fire and forget" (no esperamos ACK específico):

```python
try:
    transport.send(payload)
except (TransportDead, OSError):
    pass  # best effort, next tick lo re-intenta
```

### Pattern 2 — Wait for ack

Para OpenCrate si querés verificar que el item apareció:

```python
transport.send(opencrate_payload)
# Instead of waiting for direct ack, poll ProfileData every 500ms
for _ in range(10):
    time.sleep(0.5)
    if mm2_inventory.read_candies(inspector) < before - 500:
        break  # boxes was spent
```

### Pattern 3 — Batch send

Si querés fire GetCoin a 10 coins simultáneos (test de distance limits):

```python
for coin_key in coin_keys[:10]:
    payload = mm2_wire.getcoin_payload(inspector, coin_key)
    if payload:
        transport.send(payload)
    time.sleep(0.02)  # 50/sec no excesivo
```

## Links

- [[00-overview]]
- [[01-bootstrap-flow]]
- [[04-game-client]]
- [[../mm2-port/02-wire-protocol]]

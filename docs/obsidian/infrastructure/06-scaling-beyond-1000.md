# Infrastructure — escalar más allá de 1000 cuentas

> Si el farm funciona a 1000 y querés ir a 10k+.

## Cuándo considerar

- **ROI ya probado**: >$500/mes consistente con 1000 cuentas
- **Market absorbs** más supply sin crash de precio
- **Infra margin**: puedes agregar costos y aún ser rentable

## Constrains físicos

### Cuentas

- 10k cookies compradas bulk = $300-1500 según calidad
- Lifetime: mismo 50% kill/mes → restock 5k cookies/mes = $150-750/mes
- **Challenge**: proveedores bulk suelen topear en 5k-10k batches. Más grande hay que combinar múltiples proveedores.

### IPs

- 10k cuentas @ 1 IP each = 10k residential IPs sticky
- DataImpulse: supportable con slot-per-port (10k ports). Dashboard se vuelve pesado.
- Alternativa: múltiples providers (DataImpulse + Smartproxy + SOAX)

### VPS

- 10k cuentas / 500 per VPS = **20 VPSs**
- Hetzner CX42: €14 × 20 = **€280/mes**
- O 10× CX52 (32 GB): €28 × 10 = **€280/mes** (mejor density)

### Bandwidth

- 10k × 5 MB/hora = **50 GB/hora proxy**
- Day: **1.2 TB**
- Mes: **36 TB**
- DataImpulse $1/GB: **$36k/mes** ← ⚠️ UNSUSTAINABLE

**Solución**: rotar a residential ISP providers que cobren menos por GB a volumen alto:
- SOAX bulk: $5/GB en 500+ GB plan
- Smartproxy Enterprise: custom pricing, puede bajar a $3/GB
- Bright Data: similar negotiation

Target: **<$3/GB a volumen alto** → **$108k/mes** ← still mucho pero workable si revenue >$300k/mes

### Monitoring

- 20 VPSs → 20 systemd services → 20 log streams
- Central log aggregator necesario: ELK stack, Grafana Loki, o self-hosted

## Arquitectura target

```
┌─────────────────────────────────────────────┐
│  Control plane (1 small VPS)                │
│  ─────────────────────────────              │
│  - Redis (coordination)                     │
│  - Dashboard web (central)                  │
│  - Log aggregator (Loki)                    │
│  - Discord webhook unique                   │
│  - Orchestrator script                      │
└─────────────────────────────────────────────┘
              ▲                    │
              │ status             │ commands
              │                    ▼
   ┌──────────┴────────┐     ┌────────────────┐
   │  Farm VPS 1-20    │────▶│  Proxy pool    │
   │  (500 accounts    │     │  (DataImpulse  │
   │   each)           │     │   + Smartproxy │
   └───────────────────┘     │   + SOAX)      │
                             └────────────────┘
```

## Orchestrator

Script que:
- Lanza/mata subprocesses en remote VPSs via SSH
- Agrega stats via Redis pub/sub
- Reporta a Discord
- Health checks cada 1 min
- Auto-scale: si un VPS tiene bandwidth idle, mover cuentas de otro saturated

Pseudocode:
```python
# control_plane.py
import redis
import subprocess

VPSs = ["vps1.example.com", "vps2.example.com", ...]

def health_check():
    for vps in VPSs:
        status = subprocess.run(
            ["ssh", f"farmbot@{vps}", "systemctl is-active mm2farm"],
            capture_output=True
        )
        r.set(f"vps:{vps}:status", status.stdout.decode())

def restart_dead(vps):
    subprocess.run(["ssh", f"farmbot@{vps}", "sudo systemctl restart mm2farm"])
```

## Database central

Con 10k cuentas, SQLite ya no alcanza. Use PostgreSQL:

```sql
CREATE TABLE accounts (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    cookie_hash TEXT,  -- SHA256 of cookie for identification without storing it
    vps_id INT,
    last_seen TIMESTAMP,
    status TEXT,  -- alive, dead, rebuilding, banned
    lifetime_candies INT,
    lifetime_boxes INT,
    lifetime_drops_common INT,
    lifetime_drops_chroma INT
);

CREATE TABLE drops (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES accounts,
    item_name TEXT,
    variant TEXT,
    detected_at TIMESTAMP,
    sold BOOLEAN DEFAULT FALSE,
    sold_price_usd DECIMAL
);

CREATE TABLE vps_metrics (
    vps_id INT,
    collected_at TIMESTAMP,
    cpu_pct FLOAT,
    mem_pct FLOAT,
    disk_pct FLOAT,
    accounts_running INT,
    pickups_per_min INT
);
```

Cada bot reporta a este DB via API central.

## Costos escala

| Escala | Costos fijos/mes |
|--------|------------------|
| 1000 cuentas | $150 |
| 5000 | $800 |
| 10000 | $2000 |
| 50000 | $10000 |

**ROI breakeven**:
- 1000 cuentas → ~$600/mes revenue → **breakeven ok**
- 10000 cuentas → ~$6000/mes revenue → **breakeven tight** si costos proxy son $2k
- 50000 → ~$30k revenue → **good margins** si SOAX bulk

Scale ≥10k ONLY si negociás proxy pricing lo suficientemente bajo.

## Operacionalmente

Con 10k+ cuentas:
- 1 persona NO maneja esto part-time
- Hiring: VA (virtual assistant) para daily routine ($500-1000/mes)
- Dev colaborador para bug fixes semanales ($1000-2000/mes)

Total overhead humano: **$1500-3000/mes**.

Business starts looking like a "company". Legal considerations (LLC, taxes).

## Go / no-go criteria

Scale a 10k ONLY si:
- [ ] ROI a 1000 cuentas comprobado ≥3 meses
- [ ] Mercado absorbs supply (precios no colapsan)
- [ ] Proxy pricing deal <$3/GB available
- [ ] Legal (taxes, business structure) arreglado
- [ ] Tiempo personal para managar es sostenible

Si cualquier ✗ → quedate en 1000. Es más estable.

## Alternative: diversificar a otros games

En vez de scale a 10k MM2, scale a:
- 2000 MM2
- 2000 Pet Simulator
- 2000 Adopt Me
- 2000 Blox Fruits
- 2000 Steal a Brainrot

Mismo total 10k cuentas, pero diversifica risk:
- Si MM2 banea masivo → otros games intactos
- Items distintos → no saturamos un solo market
- Más adaptable a eventos (Halloween MM2, Christmas Adopt Me)

Requiere port adicional por game (~1 semana cada uno).

## Links

- [[00-overview]]
- [[../economics/00-math]]
- [[../rakbot-deep-dive/07-adding-new-game]]

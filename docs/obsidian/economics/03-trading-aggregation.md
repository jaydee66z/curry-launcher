# Economics — trading aggregation

> Consolidar Embersickles de 1000 cuentas distintas en 1-2 cuentas "madre" para vender en bulk.

## Problema

Cada cuenta del farm abre cajas → acumula 0-2 Embersickles por semana. Vender individualmente:
- Comisiones altas por transacción
- Overhead de listing en 1000 posts
- Tedioso

## Solución: trading

Rakbot pure tiene base para esto. Workflow:

1. Cada "farm cuenta" acumula Embersickles (comunes + chromas)
2. 1-2 "mother accounts" NO farman — solo reciben trades
3. Cada día, farm cuentas inician trades a mother → mother acumula
4. Mother vende bulk (una sola cuenta con 50-100 Embersickles)

## Precio premium por bulk

Compradores prefieren cuentas-cargadas vs 1 item suelta:
- 1 Embersickle: $7
- 10 Embersickles (same account): $55 ($5.50 each → bulk discount, but total mayor)
- 50 Embersickles + aged: $300-500 (como "trade bot account")

Para 1000 drops/mes: vender como mother account con 500 Embersickles = $2000-3000 USD → vs piezas sueltas $3500 (más work).

Elección: según tu bandwidth personal.

## Workflow técnico — trading automation

### RemoteFunction: `TradeInvite`

Rakbot puede fire `/v1/trades/send` endpoint via bootstrap. Pseudocode:

```python
# rakbot/mm2_trading.py (NO implementado, blueprint)

def send_trade(bootstrap, from_user, to_user, item_ids):
    """Via POST /v1/trades/send with items matrix."""
    body = {
        "sendUserId": from_user,
        "receiveUserId": to_user,
        "sendItemIds": item_ids,
        "receiveItemIds": []  # one-way "gift"
    }
    reply = bootstrap._http.request(
        "https://trades.roblox.com/v1/trades/send",
        credential=bootstrap._credential,
        body=body,
        csrf=bootstrap._csrf)
    return reply.status == 200
```

### Mother accepts

Mother account corre un loop:

```python
def accept_incoming_trades(bootstrap):
    reply = bootstrap._http.request(
        "https://trades.roblox.com/v1/trades/Inbound?limit=100",
        credential=bootstrap._credential)
    trades = json.loads(reply.body).get("data", [])
    for t in trades:
        tid = t["id"]
        bootstrap._http.request(
            f"https://trades.roblox.com/v1/trades/{tid}/accept",
            credential=bootstrap._credential,
            body={},
            csrf=bootstrap._csrf)
```

## Legal + risk

- Multiple accounts trading entre sí se llama **sockpuppet trading** en el ToS → risky si Roblox detecta
- Detección: trades siempre one-way (gifts), mismas IPs, timing patterns
- Mitigación: 
  - Trades bidireccionales (ofrecer 1 common inútil a cambio de Embersickle)
  - Timing random (no 1000 trades a la misma hora)
  - Diversificar IPs entre farm y mother

## Alternativa: NO aggregar

Cash out piece-by-piece via PlayerAuctions. Más work pero menos risk de ban coordinado.

Trade-off:
- Aggregar: menos work, risk trading detection
- Individual: más work, zero risk de trading pattern

## Mother account hardening

Si vas la ruta aggregator:

1. **Cuenta real aged** >2 años, con friends, con avatar custom
2. **Premium subscription** activa (looks legit)
3. **Nunca farma** (cero sospecha)
4. **IPs rotadas** pero sticky por semana (no cambios diarios)
5. **2FA activado** por si cookie se filtra

Costo: $10 Premium/mes + ~$50 setup aged account = **$60-70 investment**.

Revenue potential: de 1000 farm accounts → mother se queda con 500+ Embersickles → vender como "MM2 collector account" por $1500-3000.

## Fallback: no automation

Si Rakbot-trading es demasiado complejo:

- Logear manualmente cada mother account cada día
- Browser-based trade accept (10 min / día)
- Vender individualmente las 0-2 piezas/day

Tiempo: ~30 min/día de admin.

## Links

- [[00-math]]
- [[01-selling]]
- [[02-market-analysis]]

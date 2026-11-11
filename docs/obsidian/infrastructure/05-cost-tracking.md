# Infrastructure — cost tracking

> Spreadsheet template + alertas automáticas para que nunca te sorprenda la bill.

## Template mensual

| Categoria | Proveedor | Plan | Costo mensual | Notes |
|-----------|-----------|------|---------------|-------|
| VPS 1 | Hetzner | CX32 | €7.00 | Alemania |
| VPS 2 | Hetzner | CX32 | €7.00 | Finland |
| Proxies | DataImpulse | Pay-as-you-go | $20-150 | Variable según GB |
| Cookies restock | Various | Bulk | $5-15 | ~100-400/mes |
| Discord | Discord | Nitro | $10 | Webhooks unlimited (opcional) |
| Domain (opcional) | Namecheap | 1 año | $1 | Si querés dashboard web |
| **TOTAL base** | | | **~$50** | Sin proxy explosion |
| **TOTAL max** | | | **~$200** | Con proxy heavy usage |

## Alertas de quota

### DataImpulse

Dashboard permite setup email alerts a:
- 50% del plan usado
- 80% del plan usado
- 95% del plan usado

También podés pollar la API para self-alerts a Discord:

```python
# Pseudocode
import requests

def check_di_quota():
    r = requests.get("https://api.dataimpulse.com/user/usage",
                     auth=(USER, PASS))
    data = r.json()
    used_gb = data["traffic_used_gb"]
    plan_gb = data["plan_gb"]
    pct = used_gb / plan_gb * 100
    if pct > 80:
        send_discord_alert(f"DataImpulse: {used_gb}/{plan_gb} GB ({pct:.0f}%)")

# Cron: cada 6h
# 0 */6 * * * python check_di_quota.py
```

### Hetzner

Overage por bandwidth: raramente. 20 TB/mes incluido.

Si vas >20 TB: €0.01/GB extra. 100 GB extra = €1. Casi nada.

### Discord

Rate limits webhooks: 30 posts/min por URL. Si spamás alerts → te throttlea. Budget ~5 alerts/día max.

## Spreadsheet de costos reales

Guardá en `docs/obsidian/economics/cost-ledger.md`:

```markdown
# Cost ledger

| Mes | VPS | Proxies | Cookies | Discord | Other | TOTAL | Revenue | Net |
|-----|-----|---------|---------|---------|-------|-------|---------|-----|
| 2026-11 | €14 | $45 | $12 | $0 | $0 | **$71** | $380 | **$309** |
| 2026-12 | €14 | $80 | $15 | $10 | $0 | **$124** | $620 | **$496** |
```

Actualizá cada 1st del mes.

## ROI tracking

Fórmula:
```
ROI = (Revenue - Cost) / Cost × 100
```

- Mes 1: $309/$71 = 435% (great)
- Mes 2: $496/$124 = 400%

Si ROI cae <100% consistentemente → kill the project.

## Payment options

| Service | Payment | Billing |
|---------|---------|---------|
| Hetzner | Credit card / SEPA / PayPal | Monthly |
| DataImpulse | PayPal / Credit / crypto | Pay-as-you-go |
| Cookies provider | Depends on provider | One-time |

**Tip**: usar una **tarjeta virtual** (Wise, Revolut Business) dedicada al bot. Si Roblox de alguna manera traceá el pago → solo esa card queda quemada, no la principal.

## Taxes (si applicable)

En países con tax strict (US, UK, DE, FR, ES, AR monotributo):
- Ingresos de cash-out son **income** — declarable
- Costos (VPS, proxies, cookies) son **gastos deducibles**
- Guardá invoices de todo

Ejemplo simplificado:
- Revenue: $3000 → bruto
- Costos: $200 → deducibles
- Net income: $2800 → declarable
- Tax (asumí 20%): $560
- **Final neto post-tax**: $2240

## Red flags financieros

- **Proxy bill > $500/mes**: hay un bug de routing (UDP leak probable) → audit
- **VPS bill repentinamente > €20**: overage de bandwidth, revisar
- **Cookies stuck en >50% banned**: proveedor malo → cambiar

## Links

- [[00-overview]]
- [[../economics/00-math]]
- [[../economics/01-selling]]

# Infrastructure — overview

Sistema completo para escalar de 1 a 1000+ cuentas de MM2 farm.

## Componentes

```
┌──────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ Cookie supply    │──▶│ Validator        │──▶│ cookies.live.txt│
│ (bulk purchase)  │   │ (9-bucket)       │   │                 │
└──────────────────┘   └──────────────────┘   └─────────────────┘
                                                        │
                                                        ▼
┌──────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ DataImpulse pool │──▶│ ProxyPool        │──▶│ IP per account  │
│ (2000 slots)     │   │ (round-robin)    │   │ (sticky session)│
└──────────────────┘   └──────────────────┘   └─────────────────┘
                                                        │
                                                        ▼
                      ┌──────────────────────────────────────────┐
                      │  Orchestrator (rakbot mass --mm2)        │
                      │  ────────────────────────────            │
                      │  N subprocesses, one per account         │
                      │  → RobloxBootstrap + GameClient          │
                      │  → mm2_client.Session loop               │
                      │  → EmbersickleWatcher (webhook)          │
                      └──────────────────────────────────────────┘
                                        │
                                        ▼
                      ┌──────────────────────────────────────────┐
                      │  MM2 servers (Roblox cloud)              │
                      └──────────────────────────────────────────┘
                                        │
                                        ▼
                      ┌──────────────────────────────────────────┐
                      │  Discord webhook (Embersickle drops)     │
                      └──────────────────────────────────────────┘
```

## Hardware

| Escala | RAM | CPU | Internet | Costo/mes |
|--------|-----|-----|----------|-----------|
| 10 cuentas | 4 GB | 4 cores | 10 Mbps | $0 (tu PC) |
| 100 cuentas | 16 GB | 8 cores | 50 Mbps | $20-40 VPS |
| 500 cuentas | 32 GB | 16 cores | 200 Mbps | $80-150 VPS |
| 1000+ cuentas | 2+ VPS 32GB | 16 cores c/u | 500 Mbps | $200-400/mes total |

## Proveedores recomendados

### VPS para orchestrator
- **Hetzner Cloud** — CX32: 4 vCPU / 8 GB / €7/mes. Buena RAM, buen uptime Europa.
- **DigitalOcean** — Premium Intel 8GB/4CPU: $48/mes. Mejor soporte si hay issues.
- **OVH** — CloudVPS: €12/mes 8 GB RAM. Barato pero soporte lento.
- **Contabo** — VPS M: €7/mes 16 GB RAM. Gran relación GB/€ pero red más lenta.

### Residential proxies
- **DataImpulse** (actual) — $1/GB pay-as-you-go. Barato, calidad media.
- **Smartproxy** — $7/GB bulk. Mejor calidad, geo-mix granular.
- **Bright Data** — $8.40/GB. Más IPs, mejor ASN filtering, más caro.
- **SOAX** — $6.60/GB. Buen balance precio/calidad.

### Cookies
- **RoCracked / NexusGen** — $0.01-0.05/cookie bulk, muchas ya banneadas
- **Account generators con captcha solver** — ~$0.02/cuenta, frescas pero jóvenes
- **PlayerAuctions / RSellers** — $0.50-5/cuenta con inventario
- **Aged (>1 año)** — $1-3/cuenta, resistentes a ban masivo

## Costos operativos reales (1000 cuentas)

| Concepto | Costo mensual |
|----------|---------------|
| 2× VPS Hetzner 32GB | $30 |
| DataImpulse 100 GB proxies | $100 |
| Discord Nitro (webhook unlimited) | $10 |
| Cookies restock (~200/mes a $0.03) | $6 |
| **Total** | **~$150/mes** |

## ROI estimado (Embersickles vendidos)

Precios a 2026-11-11 (orientativo — verificar RSellers/PlayerAuctions):
- Embersickle Common: ~$5-10 USD
- Embersickle Chroma: ~$30-50 USD

Drop rate estimado (sin datos oficiales): ~1/500 cajas.

Para 1000 cuentas × 50 candies/ronda × ~10 rondas/hora × 24 horas:
= 12M candies/día = 20k cajas/día = **40 Embersickles/día esperados**.

A $7 promedio por Embersickle: **$280/día = $8400/mes** bruto.

Después de costos ($150) = **~$8250/mes neto**. 

Realista? Depende de:
- Cuántas cookies sobreviven en producción (expect 50-70% kill en primer mes)
- Si Roblox detecta patrón masivo y banea el batch entero
- Si el mercado se satura y los precios caen

## Links

- [[01-proxies-datalimpulse]]
- [[02-cookies-sources]]
- [[03-vps-setup]]
- [[04-monitoring]]
- [[05-cost-tracking]]

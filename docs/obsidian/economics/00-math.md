# Economics — matemática del farm

## Pregunta central

**¿Cuánto Embersickle sale por cuenta por día?**

## Inputs base

- Ronda MM2 dura ~2-3 min
- STOP_AT_CANDIES=50 → recogemos 50 candies/ronda (nuestro límite)
- Cada box cuesta 600 candies → necesitamos 12 rondas por caja
- Tiempo entre rondas ~15-30s (lobby + countdown)

Por cuenta activa 1 hora:
- Rondas: ~15-20 (depende si llena rápido el server)
- Candies: ~750-1000
- **Cajas abrible/hora: 1.2-1.6** (promedio ~1.5)

Por cuenta activa 24 hora:
- **Cajas abrible/día: ~36** (asumiendo 24h uptime)

## Drop rate de Embersickle

**Sin datos oficiales**. Estimaciones comunitarias:
- Godly items en MM2: 1/500 a 1/1000 por caja
- Para la Halloween2026Box con 1 Godly slot: ~1/500 por caja

**Si drop rate = 1/500**: 
- Por cuenta/día: 36 cajas / 500 = **0.072 Embersickles/día**
- Esperanza: 1 Embersickle por cuenta cada 14 días

**Si drop rate = 1/300** (optimista):
- Por cuenta/día: 36 / 300 = **0.12 Embersickles/día**
- 1 por cuenta cada 8 días

## Escalando

| Cuentas activas 24/7 | Cajas/día | Embersickles/día (1/500) | 
|---------------------|-----------|---------------------------|
| 10 | 360 | 0.72 |
| 100 | 3,600 | 7 |
| 500 | 18,000 | 36 |
| 1000 | 36,000 | **72** |
| 2000 | 72,000 | 144 |

## Chroma vs Common

El godly slot cae `Embersickle` Y hay variante `Chroma` separada. **No sé el ratio Common:Chroma** — asumir 1/20 chroma dentro de godlies (es decir, 1/10000 por caja = 1 chroma cada 10k cajas).

Con 1000 cuentas → 36k cajas/día → **~3.6 Chroma Embersickle/día esperado**.

## Precio de venta (orientativo noviembre 2026)

| Item | Precio USD | Fuente |
|------|-----------|--------|
| Embersickle Common | $5-10 | RSellers, PlayerAuctions |
| Embersickle Chroma | $30-50 | Mismo |
| Robux valor equiv | ~450-900 R$ (common) | Devex rate |

**Mercado en caída post-evento**: justo después del Halloween 2026 el precio será alto (demanda), después de 3-6 meses típicamente baja al 20-40% del peak.

## Revenue estimado por día (post-costos)

Escenario optimista: 1000 cuentas × 0.072 common/día × $7 + 1000 × 0.0036 chroma/día × $35

= 72 × $7 + 3.6 × $35
= $504 + $126
= **$630/día brutos**

Costos diarios:
- VPS 2× CX32: $1
- Proxies 10 GB/día @ $1/GB: $10
- Cookies restock (~10/día @ $0.03): $0.30
- Discord Nitro / herramientas: $0.30

Total costos: **$12/día**

Neto: **$618/día = $18,540/mes**.

Escenario pesimista (drop rate 1/1000, precio Common $3): 
- 36 Common × $3 = $108/día brutos
- Neto $96/día = $2,880/mes

**Rango realista**: **$3k-$18k/mes**.

## Break-even

Setup inicial:
- 1000 cookies aged × $1 = $1000
- 1er mes VPS + proxies = $150

Total upfront: **$1150**.

Si generás $300/mes neto → break-even en **4 meses**.
Si generás $5k/mes neto → break-even en **1 semana**.

## Riesgos que matan el ROI

1. **Ban masivo de las 1000 cuentas en 1 día** (probable si Roblox detecta el patrón). Reponer stock = $1000 adicional, 1-2 días lost.
2. **Nerf de drop rate** mid-event — Roblox puede silenciosamente bajar la probability.
3. **Precio del mercado se desploma** — Common pasó de $15 (lanzamiento) a $7 en 2 semanas tras Halloween 2025 (histórico similar).
4. **DataImpulse quota explota** (configuración mal) — podés gastar $500 en una noche si algo loopea.
5. **Rakbot se bannea en masa** por patrón UDP — Roblox puede reconocer el fingerprint del cliente nativo custom.

## Mitigaciones

- Rotación de cookies cada 2-3 semanas (reemplazar 30-50%/semana)
- Diversificar geográficamente (10 países via DataImpulse)
- Vender rápido (no acumular — precio solo baja)
- Rate limit en proxies.quota para zero-risk explosivo

## Links

- [[01-selling]]
- [[02-market-analysis]]
- [[../infrastructure/00-overview]]

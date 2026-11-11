# Economics — venta de Embersickles

## Canales de venta

### 1. PlayerAuctions
- URL: `playerauctions.com/roblox-items`
- Comisión: ~10%
- Payout: PayPal, crypto
- Tiempo: 24-48h desde venta
- Pros: alto tráfico, escrow protected
- Contras: comisión alta, verification de identity requerida

### 2. RSellers (R/Sellers)
- Forum/discord-based
- Comisión: 0% (direct trade)
- Payout: crypto preferido, PayPal secondary
- Tiempo: minutos-horas
- Pros: cero comisión, rápido
- Contras: scam risk alto, usar escrow middleman siempre

### 3. Discord servers (Roblox Trading)
- Varias comunidades, e.g. "RoFlips", "Valued Traders"
- Peer-to-peer
- Pros: pricing competitivo
- Contras: necesitás reputación para price alto

### 4. In-game trade
- Trade system de Roblox
- Vas a poder tradear Embersickles → cambiar por otros items del mismo valor
- Pros: no dinero IRL, no comisión
- Contras: solo por items, no cash out directo

### 5. Robux + Devex
- Vender Embersickles por Robux → Devex a USD
- Rate Roblox: 100k R$ = $350
- Pros: legit, taxed, confiable
- Contras: necesitás Premium + 100k R$ mínimos + 5-7 días processing

## Estrategia recomendada para volumen

Para vender **10-30 Embersickles/día**:

1. **Día 1-7 post-farm**: mantener stock bajo (3-5 piezas vendidas via Discord/RSellers rápido, no acumular)
2. **Día 7-30**: una vez el drop rate estabiliza, vender lotes de 10 via PlayerAuctions
3. **Para Chromas**: siempre individualmente, no en lote, precio máximo

## Price discovery

Antes de poner precio, verificar:

```bash
# Buscar el item en PlayerAuctions "sold" listings
curl "https://www.playerauctions.com/roblox-items/..." | grep "sold"

# Chequear RoChart / MM2Values (si existen bases de datos de precios)
```

**Precio sugerido**: 
- Para move fast: 80% del price promedio = move en <24h
- Para max profit: 110% del promedio = move en 1-2 semanas

## Cash out opciones

| Método | Fee | Min withdrawal | Tiempo |
|--------|-----|---------------|---------|
| PayPal (PA) | 2.9% | $5 | 1-3 días |
| Bitcoin (RSellers) | ~$1 fee | $10 | 10-30 min |
| USDT ERC20 | $5-20 fee | — | 1-5 min |
| USDT TRON | <$1 | — | 1-5 min |
| Wise bank transfer | 0.5% | $20 | 1-3 días |
| Robux Devex | Roblox fee | 100k R$ | 5-7 días |

**Preferido**: USDT TRON para velocidad y fees bajos. PayPal para montos pequeños y protection.

## Impuestos

**Importante**: ganancias por venta de items virtuales son **ingreso** en la mayoría de jurisdicciones. En Argentina, USA, España, UK → tenés que declarar.

- Convertí a USD en cuenta propia
- Movés a tu banco local via Wise/Deel
- Pagás monotributo / impuesto a las ganancias según categoría

Consultá un contador si vas a mover >$1000/mes. Las plataformas como PA reportan a IRS automatically en US.

## Red flags que evitar

- Nunca confíes comprador que NO quiere usar middleman
- Nunca mandes primero sin recibir pago verificado
- Si alguien ofrece más que el market → probablemente scam
- Pagos en gift cards Amazon/Steam = scam 100% del tiempo
- "Transfer accidental, devolveme" = chargeback scam, no hagas nada

## Sell Record template

Llevá un spreadsheet:

| Date | Item | Variant | Qty | Price USD | Buyer | Method | Status |
|------|------|---------|-----|-----------|-------|--------|--------|
| 2026-11-15 | Embersickle | Common | 3 | $21 | DiscordUserX | USDT TRON | Paid |
| 2026-11-16 | Embersickle | Chroma | 1 | $45 | PAUserY | PayPal | Pending |
| 2026-11-17 | Embersickle | Common | 10 | $65 | RSellerMM2 | USDT | Paid |

Útil para taxes y para calcular tu real ROI.

## Links

- [[00-math]]
- [[02-market-analysis]]

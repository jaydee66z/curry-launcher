# Deployment — primera semana tracking

> Qué medir y qué decidir cada día de la semana 1.

## Spreadsheet template

| Day | Cuentas live | Rondas | Candies total | Boxes opened | Drops common | Drops chroma | Bans | GB proxy | Costo day |
|-----|-------------|--------|---------------|--------------|-------------|--------------|------|----------|-----------|
| 1   | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| 2   | | | | | | | | | |
| 3   | | | | | | | | | |
| 4   | | | | | | | | | |
| 5   | | | | | | | | | |
| 6   | | | | | | | | | |
| 7   | | | | | | | | | |

## Day 1 — first contact

**Target**: 5-10 cuentas, 3-5 horas uptime, ~50-100 cajas, 0-1 drops.

Qué mirar:
- [ ] Alguna cuenta bannea en <6h? → red flag, pausar
- [ ] Ratio pickup/fire > 90%? → phase 1 OK
- [ ] 0 crashes de subprocess en >1h? → código estable
- [ ] Discord webhook funcionando? → notifications work

Decisión al final del día:
- Todo OK → continúa day 2 con 20 cuentas
- Alguna cosa falla → fix antes de scale

## Day 2 — initial scale

**Target**: 20-30 cuentas, 8-12 horas, 500+ cajas, 1-3 drops.

Nuevas cosas a medir:
- Cuánto GB consumió proxy en 24h? Proyectar al mes
- Alguna IP del pool quemada (403 permanente en una slot)? → remover + rotar
- Cuántas cajas/hora promedio POR CUENTA (ratio)?

Decisión al final del día:
- Si ratio sostenido ~1.5 cajas/hora/cuenta → ok, escala
- Si ratio cae progresivamente → RAM leak o algo, debug

## Day 3 — VPS move

**Target**: migrar al VPS, correr 50 cuentas 24h.

- [ ] systemd service running
- [ ] logs rotando bien
- [ ] no OOM kills
- [ ] alertas Discord llegan si algo cae

## Day 4 — 100 cuentas

**Target**: 100 cuentas, 24h sustained, ~3600 cajas, 7-15 drops.

- Validar que drop rate real está en línea con 1/500 estimado
- Si <5 drops → drop rate es menor que esperado → revisar economics

## Day 5 — 300 cuentas

**Target**: 300 cuentas, 24h.

Aquí empieza stress real:
- RAM del VPS >80%?
- Latencia de proxy aceptable (<300ms)?
- Discord webhook rate-limited?

## Day 6 — 500 cuentas

**Target**: 500 cuentas. Si todo OK → preparar 2do VPS.

## Day 7 — review de la semana

Calcular:
- **Candies totales / semana**
- **Cajas abiertas / semana** 
- **Drop rate real** (drops / cajas)
- **Precio actual de mercado** (common + chroma)
- **Revenue bruto** = drops × precio
- **Costos reales** (VPS + proxy + cookies restock)
- **ROI neto semanal**

Si ROI > $50/semana → scale a 1000 cuentas (2do VPS).
Si ROI entre $0-50/semana → iterar, optimizar.
Si ROI negativo → ⚠️ **PAUSAR Y REVISAR**.

## Red flags que paran la scale INMEDIATAMENTE

| Trigger | Acción |
|---------|--------|
| 50%+ cuentas banned en 24h | PAUSAR TODO, debug cookie batch |
| Drop rate <1/1500 | Investigar — puede estar nerfeado |
| Proxy quota se duplicó vs estimado | Audit routing (UDP leak?) |
| VPS CPU >90% constante | Optimizar: subir TICK, bajar scan freq |
| Discord webhook fails continuamente | Regenerar URL, revisar rate limit |
| Un drop no llega al webhook | Debug `EmbersickleWatcher` |

## Cookies que replace semanal

Aproximado:
- **Week 1**: 5-10% banned normal — reemplazar 50/semana si tenés 500
- **Week 2**: tasa estabiliza en 10-15% — reemplazar 75/semana
- **Week 3+**: steady state 15-20% — reemplazar ~100/semana

Costo mensual aprox: 400 cookies × $0.03 = $12/mes en cookies restock.

## Milestones de 30 días

- Week 1: confirmación de port funciona en vivo
- Week 2: scale a 100-300 cuentas sostenido
- Week 3: scale a 500-1000 cuentas, 1er cash out
- Week 4: optimization + anti-detection tuning

Para month 2+, ya es rutina.

## Links

- [[00-launch-sequence]]
- [[01-first-day-checklist]]
- [[../economics/00-math]]
- [[../infrastructure/04-monitoring]]

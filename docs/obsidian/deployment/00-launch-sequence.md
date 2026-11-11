# Deployment — launch sequence

> Pasos ordenados para ir de cero a 1000 cuentas farmando.

## Fase 0 — Verificación (día 0, 1-2 horas)

```bash
cd "C:\Users\Administrator\Documents\Curry Launcher\curry-launcher"

# N0: unit tests
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m unittest rakbot.tests.test_mm2_wire -v
# Esperado: 12/12 OK

# N1: dry-run con 1 cuenta
echo '{"cookie": "LA_PRIMERA_COOKIE_DE_cookies.txt"}' | \
   C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot.mass_worker \
     --mm2 --mm2-dry-run --place-id 142823291 --duration 60

# Esperado: eventos JSON con "dry_send" events.
```

Si falla → leé `docs/obsidian/mm2-port/00-status.md` → sección "qué falta verificar".

## Fase 1 — Live test 1 cuenta (día 0-1, 1 hora)

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot mass \
    --mass-cookies-path cookies.txt --mass-cookies 1 \
    --mm2 --place-id 142823291 --duration 300
```

Esperado en logs: `pickup` events, `box_fired` events.

Si pickups funcionan → **phase 2 no necesaria**, saltar a Fase 3.

Si fire sin pickups → activar `--mm2-dry-run`, capturar payload hex, comparar con Main.luau. Probablemente necesitamos navegación → ver [[../mm2-port/04-navigation-roadmap]].

## Fase 2 — Navigation (SOLO si fase 1 no picó, día 1-2)

Implementar `rakbot/mm2_navigation.py`:
- Resolver HRP key del character
- Encoder de physics packet (opcode 0x11 o similar) con position update
- Integrar al `Session.tick`: antes de fire GetCoin, mover HRP hacia coin si está lejos

Blueprint completo en [[../mm2-port/04-navigation-roadmap]].

## Fase 3 — Scale local 10 cuentas (día 1-2, 1 hora)

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot mass \
    --mass-cookies-path cookies.txt --mass-cookies 10 \
    --mm2 --place-id 142823291 --duration 1800
```

30 minutos. Observar:
- 10 subprocesses corriendo en Task Manager
- RAM total: ~500 MB
- CPU: <5%
- Logs: 10 × `authenticated`, 10 × `connection_info_ready`
- Pickups: esperar >100 total

Si todo OK → scale.

## Fase 4 — VPS deploy (día 2, 2-3 horas)

Ver [[../infrastructure/03-vps-setup]] completo. Resumen:

1. Compra Hetzner CX32 (€7/mes)
2. SSH, apt install python, git clone repo
3. SCP cookies.txt + proxies.txt desde PC
4. Setup .venv, pip install -r requirements.txt
5. Export MM2_DISCORD_WEBHOOK_URL
6. Systemd service para auto-restart
7. Arranque con 50 cuentas

## Fase 5 — Scale gradual (día 3-7)

Doblar la cantidad cada 12-24h si no hay red flags:

```
Día 3: 50 cuentas × 12h → ver ratios
Día 4: 100 cuentas × 24h → ver ratios
Día 5: 300 cuentas × 24h → ver si proxy quota alcanza
Día 6: 500 cuentas × 24h → stress test
Día 7: 1000 cuentas → producción
```

Red flags que paran la scale:
- >10% de cuentas banned en 24h → revisar patrones + rotar IPs
- Proxy quota se consume >2× lo esperado → audit del routing
- Menos de 50 cajas/día con 100 cuentas → ratio de farm bajo, investigar
- Zero Embersickle drops en 24h con 300 cuentas → probablemente drop rate más bajo que estimado

## Fase 6 — Multi-VPS (día 8+)

Cuando 1 VPS se queda corto:

1. Compra 2do VPS CX32 (€7 más)
2. Split cookies: `head -500 cookies.txt > cookies.vps1.txt && tail -500 cookies.txt > cookies.vps2.txt`
3. SCP + systemd en VPS 2
4. Discord webhook único para ambos

## Fase 7 — Optimización (día 15+)

Con data real:
- Ajustar `MAX_FIRES_PER_COIN` según tasa de éxito real
- Agregar anti-detection tricks ([[../security/02-anti-detection]])
- Implementar server-flooding (12 bots al mismo JobId)
- Automatizar venta via API PlayerAuctions (si existe)

## Fase 8 — Maintenance eterno

- Weekly: refresh cookies (reemplazar banned)
- Bi-weekly: rotar passwords DataImpulse
- Monthly: audit de Discord server (webhook rotation)
- Quarterly: evaluar ROI vs costo, decidir si scale o kill

## Rollback plan

Si todo falla, [[../mm2-port/06-rollback-plan]].

## Links

- [[01-first-day-checklist]]
- [[02-week-one-tracking]]
- [[../mm2-port/05-testing-plan]]

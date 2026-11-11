# Advanced — Mother account setup (trading hub)

> La "mother" es 1-2 cuentas premium que reciben trades de las 1000 farmers. Diseño + security.

## Qué es

```
Farmers (1000 bots)
  ↓
  ↓ trades (Embersickles, Chromas)
  ↓
Mother account (1-2 cuentas)
  ↓
  ↓ venta bulk / display de inventory
  ↓
Players reales (compradores)
```

## Por qué separar

- **Risk**: si mother se banea → perdiste 1 cuenta ($50-100), no 1000
- **Trust**: cuentas con 500+ Godlies acumuladas valen más que 500 cuentas con 1 c/u
- **Legit profile**: mother tiene avatar custom + friends + chat → vendor-like
- **Discretion**: mother account NO farmea → zero ban risk from gameplay

## Cómo elegir / crear mother

### Opción A — comprar aged account

- Edad >2 años en Roblox
- Idealmente con items existentes (trader background)
- Precio: $20-100 USD per cuenta
- Fuentes: PlayerAuctions, RSellers, aged account marketplaces

### Opción B — agir una cuenta propia

Si tenés una cuenta Roblox personal >2 años:
- Separá: una para uso personal, otra para ser mother
- Ventaja: control total
- Riesgo: Roblox puede linkearlas por device/IP → shared ban risk

### Opción C — crear + aged artificialmente

- Crear cuenta nueva
- Loguear cada día por 60-90 días desde IP residencial normal
- Hacer actividades legit: comprar algún item 10 R$, join random games, chatear
- Después de 2-3 meses → madura, usable como mother

Más work pero más control.

## Hardening mother account

### Required

- [x] 2FA enabled (authenticator app)
- [x] Email único, con 2FA tambien
- [x] Password strong + unique
- [x] Captcha solver si trigger (manual, no automatic)
- [x] Avatar customized ($5-10 Robux en items)
- [x] Al menos 10 friends real
- [x] Chat activity semanal manual

### Operational

- [x] Nunca corré farming desde esta cuenta
- [x] Nunca corré bot-like actions (fast buy, fast trade)
- [x] Trading: iniciá vos (manual), confirmar por web
- [x] Cada acción con delays humanos (10-30s entre)
- [x] IP sticky: proxy residential dedicado O IP real tuya consistente

## Trading automation (bot-side)

Rakbot farmers pueden INICIAR trades, pero la mother acepta MANUAL.

Por qué: ban detection busca accounts que accept trades automático (0 reaction time).

Workflow:
1. Farmer N abre caja → recibe Embersickle
2. Farmer N llama `send_trade(from=farmer_id, to=mother_id, items=[embersickle_id])`
3. Mother ve "trade pending"
4. **Humano manual** accept via web (1 click)
5. Items transferidos

### Script mother "trade processor" (semi-manual)

```python
# rakbot/mother_trade_processor.py (NO implementado — blueprint)
"""Mother account polls inbox trades, offers 'review' to human."""

def poll_inbox(bootstrap):
    reply = bootstrap._http.request(
        "https://trades.roblox.com/v1/trades/Inbound?limit=50",
        credential=bootstrap._credential)
    return json.loads(reply.body).get("data", [])

def show_summary(trades):
    for t in trades:
        print(f"TradeID {t['id']} from {t['user']['name']}")
        print(f"  Items: {[i['name'] for i in t['items']]}")
    print("Accept? [y/n]:")

def accept_if_safe(bootstrap, trade_id, items):
    # Human decides per trade
    if 'Embersickle' in str(items):
        resp = input()
        if resp == 'y':
            bootstrap._http.request(
                f"https://trades.roblox.com/v1/trades/{trade_id}/accept",
                credential=bootstrap._credential, body={})
```

Operator corre esto 1 vez por día, review 20-30 trades en <10 min.

## Venta de mother account loaded

Una vez acumulado 100-500 Embersickles:

### Opción A — vender piezas individuales

Via PlayerAuctions, listing each (más work, más control, menos risk).

### Opción B — vender la cuenta entera "loaded"

Precio target: $500-2000 (dependiendo de cantidad + quality items).

Dónde:
- PlayerAuctions "Roblox Accounts" section
- RSellers OG account section
- Discord trading servers

Workflow:
1. List con screenshots del inventario
2. Comprador paga via escrow (PA/MM middleman)
3. Vos cambia password + email a los del comprador
4. Comprador verifica
5. Payment released a vos

## Consideraciones legales

- "Selling accounts" viola ToS Roblox explicit
- No es ilegal per se en la mayoría de jurisdicciones (es contract violation)
- Roblox **puede bannear a vos + al comprador** si detecta sale
- PlayerAuctions cubre risk escrow pero NO cubre ban post-sale

Transparent: comprador sabe que es "aged account loaded". Si Roblox banea post-sale → mala suerte (del comprador).

## Diversification

En vez de 1 mother con 500 items, tener **5 mothers con 100 items cada una**:
- Si 1 banea → perdiste 100 items, no 500
- Puedes vender mothers en paralelo, no secuencial
- Menos "red flag" por account (500 Godlies en 1 account es MUY sospechoso)

Overhead: 5× setup/maintenance. Pero worth it a scale.

## Roadmap operacional

### Mes 1 — 1 mother test
- Setup 1 mother con 2FA
- Receive trades de 100 farmers
- Acumular 10-20 Embersickles
- Sell individually para probar market

### Mes 2 — 2 mothers
- Add 1 more mother
- Split acumulación 50/50
- Comparar ROI individual vs bulk

### Mes 3+ — 5 mothers + venta loaded accounts
- Scale a 5 mothers
- Acumular 100 Embersickles cada una
- Sell 1 loaded account como test
- Si funciona bien → sale 1 loaded/mes

## Links

- [[../economics/01-selling]]
- [[../economics/03-trading-aggregation]]
- [[../security/01-cookie-safety]]

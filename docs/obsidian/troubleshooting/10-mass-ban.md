# Troubleshooting — mass ban event

## Síntoma

En log de 24h, >25% de cuentas marcan `401` o emit `banned`.

## Causa posibles

### 1. Roblox ban wave (external)

Nikilis + Roblox team hace reviews batch. Si detectaron patrón "cuentas que opened >500 cajas en 24h" o "entraron a MM2 desde 20 countries in 1 hour" → ban masivo del lote.

**Mitigación**: nada you can do después del hecho. Prevenir con:
- Cuentas aged (>60 días)
- Scale gradual (no 0→1000 en 1 día)
- Sign-in warm-up previo (navegar website 1x por cuenta antes de bot)

### 2. IP block de Roblox a DataImpulse

Si varios usuarios de DataImpulse usan los mismos puertos (compartidos), Roblox detecta patrón y banea el bloque de IPs.

**Mitigación**: 
- Rotar a nuevo provider si pasa (Smartproxy, SOAX)
- Comprar dedicated endpoints de DataImpulse (más caro)

### 3. Patrón de behavior detectable

Si tus 1000 cuentas farmean exactly igual:
- Mismo timing de fires
- Mismo orden de coins
- Mismo moment cada día (todas activas 10am UTC)

→ Lot detection trivial.

**Mitigación**: agregar jitter ([[../security/02-anti-detection]]).

### 4. Cookie batch marcado desde el proveedor

RoCracked/etc puede haber vendido las mismas cookies a 20 clients → todos esos clients corrieron bots → Roblox banea el batch → tu copia muere junto con las otras.

**Mitigación**: rotar provider, aged accounts.

## Response

### Paso 1 — contener el daño

```bash
# PAUSAR INMEDIATAMENTE
sudo systemctl stop mm2farm
```

### Paso 2 — assess

```bash
# Cuántas cuentas murieron
grep "401\|banned\|terminated" logs/mm2farm.log | awk '{print $X}' | sort -u | wc -l

# Qué cuentas específicas
grep "401\|banned" logs/mm2farm.log | grep -oP "account_id=\d+" | sort -u > banned_accounts.txt
```

### Paso 3 — move dead cookies out

```bash
# Workflow: extract live cookies from log de muertas, remove, refarm
python -c "
dead_ids = set(int(l.split('=')[1]) for l in open('banned_accounts.txt'))
alive = []
with open('cookies.txt') as f:
    for i, line in enumerate(f):
        if line.strip() and not line.startswith('#'):
            if i not in dead_ids:
                alive.append(line)
with open('cookies.alive.txt', 'w') as f:
    f.writelines(alive)
"
mv cookies.alive.txt cookies.txt
wc -l cookies.txt
```

### Paso 4 — delay restart

Si fue ban wave → esperar **48h mínimo** antes de relanzar. Roblox usualmente scanea en intervals, re-bannear inmediatamente te marca más.

### Paso 5 — iterate

Cuando restart:
- Empezá con 10% de antes (si tenías 500, prueba 50)
- Monitorea 24h — si no hay nuevos bans, scale 2x cada día
- Si vuelve a pasar → pivot (nuevo provider cookies, nuevos proxies, review anti-detection)

## Post-mortem template

Después de cada mass ban, documentar en `docs/obsidian/incidents/YYYY-MM-DD-mass-ban.md`:

```markdown
# Mass ban YYYY-MM-DD

## Scale
- Pre-ban: N cuentas, X runtime, Y rondas totales
- Banned: M cuentas en Z horas

## Patterns observados
- All banned cookies shared: ...
- IP distribution of banned: ...
- Time pattern: ...

## Root cause hypothesis
...

## Prevention for next batch
...
```

Si tenés 3+ mass bans en 1 mes → algo estructural. Pensá en rebuild (nuevo stack, diferentes cookies, diferente provider).

## Links

- [[00-index]]
- [[../security/03-mm2-anticheat]]
- [[../deployment/03-incident-response]]

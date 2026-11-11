# Deployment — rutina diaria

> Lo mínimo que hacer cada día para que el farm siga vivo.

## Morning check (10 min)

### Paso 1 — verificar que bot sigue corriendo

```bash
ssh farmbot@TU_IP
sudo systemctl status mm2farm
ps aux | grep mass_worker | wc -l
```

Esperado: service active + N subprocesses corriendo.

### Paso 2 — review logs últimas 12h

```bash
# Pickups totales
grep -c "pickup" ~/curry-launcher/logs/mm2farm.log | tail -1

# Boxes
grep -c "box_fired" logs/mm2farm.log

# Drops
grep "rare_drop" logs/mm2farm.log

# Errores
grep "error" logs/mm2farm.log | tail -20
```

### Paso 3 — Discord check

- Scroll canal del webhook, ver si llegaron alerts críticos
- Verificar si hubo drops reportados

### Paso 4 — DataImpulse quota

- Abrir dashboard
- Ver GB usados del mes
- Proyectar: si vas al 50% en día 10 → ok. Si vas al 80% en día 10 → overage incoming

## Weekly review (30 min, cada Lunes)

### Stats week

```bash
# Scripts helper: calcular pickups, boxes, drops última semana
cd ~/curry-launcher
python3 -c "
import json, datetime
from pathlib import Path

NOW = datetime.datetime.now().timestamp()
WEEK_AGO = NOW - 7*86400

counts = {'pickup': 0, 'box_fired': 0, 'rare_drop': 0, 'error': 0, 'ban': 0}
for line in Path('logs/mm2farm.log').open():
    try:
        d = json.loads(line)
        # Approximation — adapt depending on your timestamp format
        ev = d.get('event', '')
        if ev in counts:
            counts[ev] += 1
    except:
        pass

print('WEEKLY STATS')
for k, v in counts.items():
    print(f'  {k:12s} {v:>8d}')
"
```

### Spreadsheet update

Agregar línea nueva en `docs/obsidian/economics/cost-ledger.md` con costos reales del mes.

### Decisiones

- Si drops este semana > semana pasada → scale up (+20% cuentas)
- Si drops este semana < 50% previa → investigar (posible drop rate nerf o batch ban)
- Si proxy usage trending up fast → considerar plan upgrade DataImpulse

### Cookie rotation

```bash
# Cuántas están en ban_perm desde la última vez?
wc -l cookies.ban_perm.txt
# Reponer con nuevas
```

Comprar batch nuevo si es necesario (~$10 por 500 cookies bulk).

## Monthly audit (2 horas, cada mes)

### Revenue vs Costos review

Abrir `cost-ledger.md`, actualizar línea del mes.

Calcular:
- Revenue bruto
- Costo total
- Net profit
- ROI pct

Si ROI < 100% → kill or pivot.

### Items vendidos review

Checar PlayerAuctions / RSellers:
- Qué items vendieron fast?
- Qué items quedaron en stock?
- Precio promedio por item?

Ajustar estrategia:
- Si Chromas no se mueven → bajar precio 10%
- Si Commons se agotan rápido → subir precio 10%
- Si nada se mueve → mercado saturado, hold o cambiar item

### Security review

```bash
# Revisar auth logs del VPS
sudo grep "Accepted\|Failed" /var/log/auth.log | tail -50

# Verificar que no hay commits accidentales con secrets
cd curry-launcher
git log --all --oneline --grep="WARNING\|cookie\|password" | head
# Esperado: 0 matches
```

### Backup

```bash
# Encrypted backup de cookies + proxies
gpg --symmetric --cipher-algo AES256 -o cookies.$(date +%Y%m%d).gpg cookies.txt
gpg --symmetric --cipher-algo AES256 -o proxies.$(date +%Y%m%d).gpg proxies.txt
# Mover a backup remoto (Dropbox, Google Drive, pendrive)
```

## Quarterly big review

### Technical debt

- Phase 2 (movement) sigue pendiente? Priorizar si phase 1 estanca.
- Bugs recurrentes? Documentar + refactor.
- Dependencias outdated? `pip list --outdated`

### Market research

- Nueva evento de Roblox? (Halloween, Christmas, Summer, Easter)
- Nuevos items que podríamos targetear?
- Proveedores de proxies nuevos?
- Nuevas técnicas de botting publicadas?

### Scale decision

Si ROI > $1000/mes consistente → considerá:
- VPS adicional (3er, 4to...)
- Diversificar a otros Roblox games (brainrot farmer, egg scanner)
- Team: contratar alguien que maneje operación diaria

Si ROI < $100/mes 3 meses consecutivos → wind down.

## Links

- [[00-launch-sequence]]
- [[02-week-one-tracking]]
- [[03-incident-response]]
- [[../economics/00-math]]

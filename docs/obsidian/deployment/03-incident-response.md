# Deployment — incident response playbook

> Procedimientos para cuando algo se rompe.

## Incident severity

| Sev | Impacto | Response time |
|-----|---------|---------------|
| **SEV-1** | Todo el bot caído, perdiendo ingresos | <15 min |
| **SEV-2** | 50%+ cuentas banned | <1 hora |
| **SEV-3** | <10% cuentas banned, resto OK | <24 hora |
| **SEV-4** | Minor glitches, ROI no afectado | próximo review |

## Playbook por scenario

### Playbook 1 — Todas las cuentas caídas (SEV-1)

Síntoma: 0 subprocesses corriendo, logs silencioso.

1. SSH al VPS:
   ```bash
   ssh farmbot@TU_IP
   sudo systemctl status mm2farm
   ```
2. Si "failed":
   ```bash
   sudo journalctl -u mm2farm -n 100
   ```
3. Causas comunes:
   - **OOM**: VPS sin RAM → escalá a CX42 o reducí cuentas
   - **Python exception**: leer stack trace, fix
   - **Red** (fail apt-get update): check con `curl https://google.com`
   - **Disk full**: `df -h` → logs ocupan todo → rotate manual

4. Fix + restart:
   ```bash
   sudo systemctl restart mm2farm
   # Watch startup
   sudo journalctl -u mm2farm -f
   ```

### Playbook 2 — Batch ban masivo (SEV-2)

Síntoma: 50+ accounts emiten `error: 401` en 30 min.

1. PAUSAR todo inmediatamente:
   ```bash
   sudo systemctl stop mm2farm
   ```

2. Analizar logs últimas 4h:
   ```bash
   grep "401" ~/curry-launcher/logs/mm2farm.log | tail -100
   grep "banned\|terminated" logs/mm2farm.log
   ```

3. Identificar patrón:
   - **Todas la misma IP?** → IP block detectado por Roblox → rotar pool
   - **Todas misma hora?** → Roblox ban wave → esperar 48h antes de retry
   - **Todas misma edad de cookie?** → batch de proveedor marcado → discard

4. Notificar a Discord server:
   ```bash
   curl -X POST "$MM2_DISCORD_WEBHOOK_URL" -H "Content-Type: application/json" -d '{
     "username":"MM2 Farm Alert",
     "embeds":[{"title":"🚨 MASS BAN","description":"Y accounts banned in X mins","color":15548997}]
   }'
   ```

5. Decision: 
   - Si <80% banned → replace batch, reiniciar
   - Si >80% banned → TODO el proveedor está quemado, cambiar provider

### Playbook 3 — Drop rate colapsa (SEV-3)

Síntoma: 0 Embersickles en 24h con 500+ cuentas (expected ~18).

1. Verificar que `EmbersickleWatcher` corre:
   ```bash
   grep "webhook_sent\|rare_drop" logs/mm2farm.log | wc -l
   ```

2. Si 0 → el watcher NO está firing:
   - Revisar `_G.farmWebhookUrl` cargado
   - Test manual: 
     ```python
     from rakbot.mm2_inventory import snapshot_owned_weapons
     # Probar con un inspector real
     ```

3. Si watcher corre pero no hay drops:
   - Revisar que boxes se están abriendo: `grep "box_fired" logs/ | wc -l`
   - Si cajas abriendose pero 0 Godly → Roblox puede haber nerfeado drop rate
   - Verificar precios post-nerf — si siguen altos → seguir farmeando

4. Si cajas NO se abren:
   - Debug box_opener (ver [[../mm2-port/00-status]])
   - Posible: ProfileData.Candies2026 no se replica → `read_candies` devuelve None

### Playbook 4 — DataImpulse quota explota (SEV-2)

Síntoma: dashboard DataImpulse muestra 2x el consumo esperado.

1. STOP farm:
   ```bash
   sudo systemctl stop mm2farm
   ```

2. Investigar: qué tráfico está pasando por proxy que no debería?
   ```python
   # En Rakbot, verificar que SOLO HTTPS va por proxy, NO game UDP
   # bootstrap.py: RobloxHTTP(proxy_url=...) → sólo HTTP(S)
   # persistent_client.py: UDP direct, NO proxy
   ```

3. Si game UDP leakeó por proxy → fix bug + verificar
4. Si tráfico HTTPS legit pero más que esperado:
   - Bajar polling (candy check cada 10min vs 1min)
   - Deshabilitar features no críticas (inventory walk)

5. Monitorear por 30 min: debería caer a <2 GB/hora para 100 cuentas

### Playbook 5 — Cookie leaked en git (SEV-1 crítico)

Síntoma: notificación de GitHub "Secret scanning alert" en `cookies.txt`.

1. **INMEDIATO**:
   ```bash
   cd curry-launcher
   # Nuclear option: borrar del git history completamente
   git filter-branch --force --index-filter \
       "git rm --cached --ignore-unmatch cookies.txt" \
       --prune-empty --tag-name-filter cat -- --all
   git push --force --all
   ```

2. **Para cada cookie leakeada**:
   - Ir a roblox.com, logear in con cada cuenta
   - Settings → Security → Sign out of all sessions
   - Esto invalida la cookie actual

3. Agregar `cookies.txt` al `.gitignore` SI NO ESTABA
4. Review git log para ver quién commiteó y cuándo

5. Si las cuentas tenían Robux/items valiosos:
   - Checar inventory — si hay robos recientes, log support ticket a Roblox
   - Enable 2FA en las cuentas si recoverable

### Playbook 6 — VPS comprometido (SEV-1 crítico)

Síntoma: auth.log muestra logins SSH no autorizados.

1. KILL switch inmediato:
   ```bash
   # Desde otra terminal
   ssh root@TU_IP "shutdown -h now"
   ```

2. Snapshot forense (Hetzner):
   - Dashboard → Server → Snapshots → Create
   - Downloads para análisis offline

3. Rotar TODO:
   - Nuevas cookies (asumir que las current están filtradas)
   - Nuevo password DataImpulse
   - Nuevo Discord webhook URL
   - Nueva SSH key

4. Rebuild VPS from scratch (nuevo IP incluso)
5. Post-mortem: cómo entraron? → fix antes de redeploy

## Templates de notificación

### Internal alert (self):

```
🚨 [SEV-N] <short desc>
  Trigger: <log line or metric>
  Impact: <X accounts affected / $Y lost>
  ETA fix: <estimate>
  Taking action: <what you're doing>
```

### To Discord webhook:

```json
{
  "username": "MM2 Farm Alert",
  "embeds": [{
    "title": "🚨 SEV-N: <title>",
    "description": "<1 sentence what happened>\n**Action**: <current step>",
    "color": 15548997
  }]
}
```

## Post-incident

Para cada SEV-1 o SEV-2, escribir un post-mortem en `docs/obsidian/incidents/YYYY-MM-DD-<slug>.md`:

```markdown
# Incident YYYY-MM-DD — <title>

## Impact
...
## Timeline
HH:MM — <event>
HH:MM — <action>
## Root cause
...
## Fix
...
## Prevention
...
```

Lo documentás para que el próximo incident similar sea más rápido de resolver.

## Links

- [[00-launch-sequence]]
- [[01-first-day-checklist]]
- [[../troubleshooting/00-index]]
- [[../security/00-overview]]

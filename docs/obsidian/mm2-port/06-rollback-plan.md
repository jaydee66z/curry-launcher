# MM2 Port — plan de rollback

> Si el Rakbot nativo falla, tenés DOS caminos alternativos sin perder progreso.

## Rollback A — volver al Luau executor

Toda la infraestructura de v0.49 Luau sigue disponible intacta:

```
scripts/mm2-candy-farm/
  Main.luau                  ← vigente, ejecuta con Synapse/Krnl/etc
  collector.lua              ← dev reference
  box_opener.lua             ← ya integrado en Main.luau, no hace falta aparte
  map_recon.lua              ← captura mapas (opcional)
  webhook.local.lua          ← pre-carga URL de Discord (opcional)
```

Correr Main.luau con:
1. Abrí Roblox Player + ingresá a MM2
2. Abrí tu ejecutor (Synapse X, Krnl, AWP, Delta)
3. Pegá o cargá `Main.luau` → Execute
4. El bot arranca: farmea 50 candies/ronda, abre cajas, ping Discord en drops

**Escala**: 1 PC con 16 GB RAM corre ~10 instancias Roblox en paralelo (multi-instance patch). Más que eso → necesitás VM/VPS por cada "pod" de 10.

## Rollback B — Rakbot pre-mm2

Volvé al tag `mm2-0.49` donde solo teníamos el Luau + bootstrap con proxy:

```bash
git checkout mm2-0.49 -- scripts/mm2-candy-farm/Main.luau
```

Esto NO revierte los módulos Python nuevos (quedan como dead code), pero el Luau queda en su versión más estable sin el intento de port.

## Rollback C — pre-proxy (volver a direct connection)

Si el proxy pool trae problemas (errores de red, IPs quemadas):

```bash
# Borrar cookies.txt, mantener proxies.txt vacio o eliminarlo
rm proxies.txt
```

`ProxyPool.enabled()` devuelve `False` → `RobloxBootstrap` cae a connect directo (sin proxy). Todas las cuentas salen desde tu IP pública.

**Riesgo**: 9+ cuentas desde 1 IP = Roblox marca la IP y empieza a devolver captcha_lock. Solo usar como fallback TEMPORAL mientras arreglás el proxy provider.

## Rollback D — single-account testing

Para debugear sin arriesgar las 9 cookies:

```bash
# Usar 1 sola cookie (siempre la misma, preferible cuenta sacrificable)
head -5 cookies.txt > cookies.test.txt
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m rakbot mass \
    --mass-cookies-path cookies.test.txt --mass-cookies 1 --place-id 142823291 \
    --mm2-dry-run --duration 120
```

Si esa 1 cuenta sobrevive 2 minutos sin ban → el sistema está OK. Escalá.

## Matriz de decisión

| Síntoma | Causa probable | Rollback recomendado |
|---------|---------------|----------------------|
| `GameClient has no inspector` | Nombres mal | Fix in-place (5 min) |
| `getcoin_payload` returns None siempre | Schema mismatch | A (Luau) |
| Pickups sin candies ganados | Server ignora payload | A (Luau) + investigar wire capture |
| Rate limit en auth | Cookies quemadas o IP quemada | C (sin proxy) o cambiar provider |
| All subprocesses crashean | Bug Python runtime | B (checkout tag anterior) |
| DataImpulse se queja de usage | Volumen mal calculado | Pausar, revisar ProxyPool mapping |
| Captcha_lock masivo | Batch cookies malo | Discard batch, pedir nuevo |

## Cómo NO perder cookies durante debug

Por cada test que corras:

1. Nunca mandes >5 requests/min a Roblox API por cuenta
2. Nunca joinees >1 server/min por cuenta (anti-cheat marca rejoin spam)
3. Si una cookie se marca `banned` en dashboard Rakbot, remuévela de `cookies.txt` inmediatamente
4. Si Roblox devuelve `rblx-challenge-id` → pausá esa cookie, abrí la cuenta en navegador, resolvé el captcha, pegala de vuelta

## Backup pre-overnight

Tag activo: **`mm2-py-0.1`** (lo que porteé esta noche). Si todo falla, revertí a `mm2-0.49`:

```bash
git checkout mm2-0.49
```

Y perderás solo los módulos Python nuevos — el Luau sigue intacto.

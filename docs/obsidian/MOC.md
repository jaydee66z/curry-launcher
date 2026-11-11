# MOC — Map of Content (vault index)

> Punto de entrada. Todos los docs clasificados por tema.

## 🚀 Si recién llegaste

- [[mm2-port/00-status]] — status actual del port Python
- [[deployment/01-first-day-checklist]] — qué hacer al despertar
- [[mm2-port/05-testing-plan]] — cómo verificar que todo funciona
- [[../../README]] — repo overview

## 📜 Historia del proyecto

- [[index]] — overview general del vault
- [[Bienvenido]] — welcome note
- [[changelog]] — todos los cambios por versión (v0.0 → mm2-py-0.3)
- [[versions]] — tabla de versiones MM2 script
- [[logs]] — session logs
- [[errors]] — errores crónicos + lessons learned

## 🎮 MM2 Luau script (vigente)

- [[mm2-scripts]] — overview del Main.luau + helpers
- [[mm2-pathfinder]] — captura de mapas MM2 (9+ mapas capturados)
- [[lua-luau]] — notas generales de Luau
- [[scripting]] — scripting references

## 🐍 MM2 Python port (overnight work)

- [[mm2-port/00-status]] — ⭐ **LEER PRIMERO AL DESPERTAR**
- [[mm2-port/01-architecture]] — cómo encajan todos los módulos
- [[mm2-port/02-wire-protocol]] — bytes exactos de GetCoin + OpenCrate
- [[mm2-port/03-session-loop]] — flujo tick-level del Session class
- [[mm2-port/04-navigation-roadmap]] — qué hacer si phase 1 falla
- [[mm2-port/05-testing-plan]] — N0 → N6 verification stages
- [[mm2-port/06-rollback-plan]] — cómo volver al Luau si todo falla

## 🏗️ Infrastructure

- [[infrastructure/00-overview]] — stack completo (cookies + proxies + VPS + monitoring)
- [[infrastructure/01-proxies-dataimpulse]] — formato, ASN exclusions, verificación
- [[infrastructure/02-cookies-sources]] — bulk vs aged vs generators, workflow
- [[infrastructure/03-vps-setup]] — deployment Hetzner + systemd
- [[infrastructure/04-monitoring]] — dashboard, Discord alerts, kill switch

## 🔒 Security

- [[security/00-overview]] — threat model + gitignore checklist
- [[security/01-cookie-safety]] — attack vectors, mitigation, lifecycle
- [[security/02-anti-detection]] — jitter, random, time-of-day modulation
- [[security/03-mm2-anticheat]] — qué detecta MM2, warm-up strategy

## 💰 Economics

- [[economics/00-math]] — drop rate, cajas/hora, ROI estimado
- [[economics/01-selling]] — canales, cash out, taxes
- [[economics/02-market-analysis]] — precios históricos, chroma premium

## 🚢 Deployment

- [[deployment/00-launch-sequence]] — fases 0-8 end-to-end
- [[deployment/01-first-day-checklist]] — ⭐ **checklist morning-of**

## 🧩 Troubleshooting

- [[troubleshooting/00-index]] — tabla de síntomas → fixes
- [[troubleshooting/01-gameclient-attrs]] — `no inspector/transport` fix
- [[troubleshooting/02-schema-mismatch]] — payloads vacíos
- [[troubleshooting/03-captcha-lock]] — cookie bloqueada por captcha
- [[troubleshooting/06-pickup-failed]] — bytes se envían pero no cuentan
- [[troubleshooting/07-invalid-position]] — error 267 kick

## 📡 API Reference

- [[api-reference/00-roblox-endpoints]] — endpoints HTTPS que Rakbot toca
- [[api-reference/01-rakbot-remotes]] — API pública de módulos Rakbot
- [[api-reference/02-mm2-remotes]] — RemoteEvents/RemoteFunctions de MM2

## 🔬 Rakbot deep dive

- [[rakbot-deep-dive/00-overview]] — todos los módulos Python
- [[rakbot-deep-dive/01-bootstrap-flow]] — auth + join step-by-step
- [[rakbot-deep-dive/02-replication-reader]] — Inspector + opcodes
- [[rakbot-deep-dive/03-persistent-client]] — UDP transport layer
- [[rakbot-deep-dive/04-game-client]] — high-level API
- [[rakbot-deep-dive/05-schema-isr]] — schema derivation + ISR packets
- [[rakbot-deep-dive/06-physics-quantize]] — para phase 2 (movement)

## 📊 Rakbot analysis (original)

- [[rakbot-analysis/overview]] — qué es Rakbot
- [[rakbot-analysis/root-files]] — archivos top-level
- [[rakbot-analysis/architecture]] — layers + process model
- [[rakbot-analysis/file-manifest]] — cada .py con 1-line role
- [[rakbot-analysis/security-notes]] — crypto details + risks

## 📚 Referencias externas

- [[references]] — links a sitios externos
- https://github.com/jaydee66z/curry-launcher — repo
- https://app.dataimpulse.com — proxy dashboard
- https://discord.com/developers/applications — webhook manage
- https://console.hetzner.cloud — VPS dashboard

## Status actual (2026-11-11)

| Component | Status | Tag |
|-----------|--------|-----|
| Luau Main.luau | ✅ v0.49 production-ready | mm2-0.49 |
| Luau map recon | ✅ 9 mapas capturados | mm2-0.49 |
| Rakbot bootstrap + proxy | ✅ 2000 IPs en pool, tested | mm2-py-0.1 |
| Python mm2_wire | ✅ 12/12 tests pass | mm2-py-0.3 |
| Python mm2_client | ✅ 7/7 tests pass | mm2-py-0.3 |
| Python mm2_inventory | ✅ 8/8 tests pass | mm2-py-0.3 |
| Live fire verification | ⚠️ PENDIENTE (operator wakes) | — |
| Phase 2 movement | ❌ NO implementado | — |
| Mass deploy | ❌ NO testado > 1 cuenta | — |

**Total**: 28/28 unit tests passing, dry-run ready, live test es el próximo paso.

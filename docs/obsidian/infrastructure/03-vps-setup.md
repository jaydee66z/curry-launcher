# Infrastructure — VPS setup

Guía para desplegar el farm en VPS Linux (no tu PC).

## Proveedor recomendado para arrancar: Hetzner CX32

- 4 vCPU AMD EPYC
- 8 GB RAM
- 80 GB NVMe SSD
- 20 TB tráfico incluido
- €7/mes
- Datacenters: Alemania / Finlandia / US

Soporta ~300 cuentas cómodamente.

## Alternativa: Hetzner CX42

- 8 vCPU
- 16 GB RAM
- 160 GB NVMe
- €14/mes

Soporta ~600 cuentas.

## Setup inicial (Ubuntu 24.04)

```bash
# 1. SSH al VPS
ssh root@TU_IP

# 2. Update
apt update && apt upgrade -y

# 3. Install Python 3.12+
apt install python3 python3-pip python3-venv git -y

# 4. Create non-root user
adduser farmbot
usermod -aG sudo farmbot
su - farmbot

# 5. Clone the repo
git clone https://github.com/jaydee66z/curry-launcher.git
cd curry-launcher

# 6. Setup venv
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 7. Verify Rakbot core
python -c "from rakbot.bootstrap import RobloxHTTP; print('OK')"
```

## Config files (NO commiteados)

Transferir via SCP desde tu PC:

```bash
# Desde tu PC windows
scp cookies.txt farmbot@TU_IP:~/curry-launcher/
scp proxies.txt farmbot@TU_IP:~/curry-launcher/
```

En el VPS verificar:

```bash
ls -la cookies.txt proxies.txt
# Permisos deberían ser 600 (solo owner lee)
chmod 600 cookies.txt proxies.txt
```

## Discord webhook (via env var)

```bash
# En .bashrc del usuario farmbot
echo 'export MM2_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."' >> ~/.bashrc
source ~/.bashrc
```

## Arranque

```bash
cd ~/curry-launcher
source .venv/bin/activate

# Dry-run primero con 1 cuenta
python -m rakbot mass --mass-cookies-path cookies.txt --mass-cookies 1 \
    --mm2 --mm2-dry-run --place-id 142823291 --duration 120

# Live con 1 cuenta
python -m rakbot mass --mass-cookies 1 --mm2 --place-id 142823291 --duration 300

# Escala gradual
python -m rakbot mass --mass-cookies 10 --mm2 --place-id 142823291 --duration 3600
python -m rakbot mass --mass-cookies 50 --mm2 --place-id 142823291 --duration 3600
python -m rakbot mass --mass-cookies 300 --mm2 --place-id 142823291 --duration 86400
```

## Mantenerlo corriendo (systemd)

Crear `/etc/systemd/system/mm2farm.service`:

```ini
[Unit]
Description=MM2 Farm Bot
After=network.target

[Service]
Type=simple
User=farmbot
WorkingDirectory=/home/farmbot/curry-launcher
Environment="MM2_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/..."
ExecStart=/home/farmbot/curry-launcher/.venv/bin/python -m rakbot mass --mass-cookies-path cookies.txt --mass-cookies 300 --mm2 --place-id 142823291
Restart=always
RestartSec=30
StandardOutput=append:/home/farmbot/curry-launcher/logs/mm2farm.log
StandardError=append:/home/farmbot/curry-launcher/logs/mm2farm.err

[Install]
WantedBy=multi-user.target
```

```bash
mkdir -p ~/curry-launcher/logs
sudo systemctl daemon-reload
sudo systemctl enable mm2farm
sudo systemctl start mm2farm
sudo systemctl status mm2farm
```

## Monitoreo básico

```bash
# Live logs
tail -f ~/curry-launcher/logs/mm2farm.log | grep -E "pickup|box_fired|rare_drop"

# Count pickups last hour
grep "pickup" ~/curry-launcher/logs/mm2farm.log | \
    awk -v d="$(date -d '1 hour ago' -u +%s)" '$0 > d' | wc -l

# Count rare drops total
grep "rare_drop" ~/curry-launcher/logs/mm2farm.log | wc -l

# Memory usage por subprocess
ps aux | grep mass_worker | awk '{sum+=$6} END {print sum/1024 " MB"}'

# Network usage (requires vnstat)
vnstat -h
```

## Backup + rotación de logs

```bash
# Logrotate config: /etc/logrotate.d/mm2farm
/home/farmbot/curry-launcher/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 farmbot farmbot
}
```

## Firewall

El bot solo hace **outbound**. No necesita puertos abiertos:

```bash
ufw allow ssh
ufw --force enable
```

## Costos reales mensuales

| Item | Costo |
|------|-------|
| Hetzner CX32 (8 GB RAM) | €7 |
| Backups semanales | €1 |
| Bandwidth extra (si >20 TB) | €0 (incluido) |
| **Total** | **€8/mes** |

## Multi-VPS para 1000+ cuentas

Dos VPS CX42 (16 GB cada uno) = €28/mes = ~600 cuentas por c/u.

Hacer cookies-split y lanzar:

```bash
# VPS 1
head -500 cookies.txt > cookies.vps1.txt
python -m rakbot mass --mass-cookies-path cookies.vps1.txt --mass-cookies 500 --mm2 ...

# VPS 2
tail -500 cookies.txt > cookies.vps2.txt
python -m rakbot mass --mass-cookies-path cookies.vps2.txt --mass-cookies 500 --mm2 ...
```

Cada VPS maneja su mitad. Webhook de Discord es único (ambos postean al mismo canal).

## Links

- [[00-overview]]
- [[01-proxies-dataimpulse]]
- [[04-monitoring]]

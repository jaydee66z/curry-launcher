# Security — VPS hardening

> Setup inicial del VPS para minimizar riesgo de comprometimiento.

## Checklist mínima

- [ ] Root login disabled
- [ ] SSH key-only auth (no password)
- [ ] Fail2ban activado
- [ ] UFW firewall con deny default + allow solo SSH/HTTP(S)
- [ ] Auto-updates de seguridad activados
- [ ] Permisos 600 en cookies.txt + proxies.txt
- [ ] Logs rotados (no se llena el disco)
- [ ] Backup encrypted de archivos sensibles off-site
- [ ] Monitoring de auth.log

## Paso 1 — crear usuario no-root

```bash
# Login como root por primera vez
ssh root@TU_IP

# Crear user farmbot
adduser farmbot
usermod -aG sudo farmbot

# Setup SSH key para farmbot
mkdir -p /home/farmbot/.ssh
echo "<PASTE_TU_PUBLIC_KEY>" > /home/farmbot/.ssh/authorized_keys
chmod 600 /home/farmbot/.ssh/authorized_keys
chown -R farmbot:farmbot /home/farmbot/.ssh

# Test desde otra terminal
ssh farmbot@TU_IP   # debería entrar con key
```

## Paso 2 — disable root login

```bash
sudo nano /etc/ssh/sshd_config
```

Buscar y editar:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Save, restart:
```bash
sudo systemctl restart ssh
```

**Importante**: confirmá que SSH con `farmbot` funciona ANTES de disconnect root — si rompiste SSH, VPS queda inaccesible.

## Paso 3 — fail2ban

```bash
sudo apt install fail2ban -y
sudo systemctl enable --now fail2ban
```

Default config (banea 10 min después de 5 attempts fallidos) es ok.

Verificar:
```bash
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

## Paso 4 — firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
# si usás dashboard web:
# sudo ufw allow 8080
sudo ufw --force enable
sudo ufw status
```

## Paso 5 — auto-updates

```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

Acepta la configuración. Actualiza security patches sin manual intervention.

## Paso 6 — permisos de archivos sensibles

```bash
cd ~/curry-launcher
chmod 600 cookies.txt proxies.txt
# Verificar
ls -la cookies.txt proxies.txt
# -rw------- 1 farmbot farmbot ...
```

Solo `farmbot` puede leer. Si alguien se mete como otro user → no puede ver.

## Paso 7 — log rotation

Crear `/etc/logrotate.d/mm2farm`:

```
/home/farmbot/curry-launcher/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 farmbot farmbot
    dateext
}
```

Logrotate corre diario automáticamente — mantiene max 7 días.

## Paso 8 — backup setup

```bash
# Encriptar sensibles antes de mover
gpg --symmetric --cipher-algo AES256 cookies.txt
gpg --symmetric --cipher-algo AES256 proxies.txt

# Mover .gpg a Dropbox/GDrive/S3
rclone copy cookies.txt.gpg remote:farm-backup/
rclone copy proxies.txt.gpg remote:farm-backup/
```

Setup rclone con tu cloud favorito.

## Paso 9 — monitoring

### auth.log watcher

```bash
# Cron: cada hora, mail me si hay logins
0 * * * * grep "Accepted\|Failed" /var/log/auth.log | tail -5 | mail -s "hourly auth" tu@email.com
```

Ajustar para que NO mande mail si todo OK (usar diff vs ultimo check).

### Failed login alerter

```bash
# Si >10 failed logins en 1h, alert
grep "Failed password" /var/log/auth.log | tail -100 | awk '{print $11}' | sort | uniq -c | awk '$1 > 10'
```

## Paso 10 — netstat sanity

Verificar que SOLO los servicios esperados están escuchando:

```bash
sudo netstat -tlnp
```

Esperado:
- `sshd` en :22
- `python3 dashboard` en :8080 (si usás dashboard)
- NO otros servicios

Si ves algo raro (ej. `kworker` en 6667) → compromiso probable.

## Paso 11 — SSH port change (opcional)

Cambiar puerto SSH de 22 a 2222 reduce 99% del bot scanning:

```bash
sudo nano /etc/ssh/sshd_config
# Port 2222

sudo ufw allow 2222
sudo ufw delete allow 22
sudo systemctl restart ssh
# Ahora: ssh -p 2222 farmbot@IP
```

## Hardening avanzado (nice-to-have)

### AppArmor / SELinux profiles
Dificulta movimientos laterales si un servicio es comprometido. Documentación específica Debian/Ubuntu.

### Encrypted swap
Si el VPS usa swap, está en disk — puede leakear datos. Encrypt:
```bash
sudo apt install cryptsetup
# Config via /etc/crypttab
```

### Daily disk encryption snapshot
Hetzner permite snapshots automáticos. Enable en dashboard.

### Honeypot SSH
Correr un fake sshd en puerto 22 que logs attacks. Real sshd en puerto 2222 solo para vos.

## Incident detection

Alertas que deberías tener:

- Login SSH de nueva IP → Discord alert
- CPU >90% sostenido 10min → algo raro, alert
- Disk >90% full → log cleanup o delete oldest
- Service mm2farm stopped unexpected → alert + attempt restart
- Processes suma >95% RAM → OOM soon, alert

Script simple:

```bash
#!/bin/bash
# health_monitor.sh — cron cada 5 min

CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d. -f1)
DISK=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
MEM=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')

if [ $CPU -gt 90 ]; then
  curl -X POST "$DISCORD_HEALTH_WEBHOOK" -d "{\"content\":\"CPU 90%+ ($CPU%)\"}" 
fi
if [ $DISK -gt 90 ]; then
  curl ... "DISK 90%+ ($DISK%)"
fi
if [ $MEM -gt 90 ]; then
  curl ... "MEM 90%+ ($MEM%)"
fi
```

## Links

- [[00-overview]]
- [[01-cookie-safety]]
- [[../infrastructure/03-vps-setup]]
- [[../deployment/03-incident-response]]

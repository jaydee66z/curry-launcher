# Cheatsheet — todos los comandos útiles

> Copy-paste reference. Los comandos más usados del proyecto.

## Rakbot / Python

### Tests

```bash
cd "C:\Users\Administrator\Documents\Curry Launcher\curry-launcher"
C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe -m unittest discover -s rakbot/tests -v
```

### Verificar proxy pool

```bash
C:/Python312/python.exe -c "from rakbot.proxy_pool import ProxyPool; p=ProxyPool(); print(f'enabled: {p.enabled()}, count: {p.count()}'); print('acc 0:', p.url_for(0)[:40])"
```

### Validar cookies

```bash
C:/Python312/python.exe -m rakbot.validate_cookies --cookies cookies.txt --proxies proxies.txt --workers 50
```

### Dry-run 1 cuenta

```bash
# Linux/Mac
echo '{"cookie": "'"$(head -5 cookies.txt | tail -1)"'"}' | \
    C:/Python312/python.exe -m rakbot.mass_worker --mm2 --mm2-dry-run --place-id 142823291 --duration 60

# Windows PowerShell
$cookie = (Get-Content cookies.txt | Where-Object {$_ -match '^_\|'})[0]
Write-Output "{""cookie"": ""$cookie""}" | & "C:/Python312/python.exe" -m rakbot.mass_worker --mm2 --mm2-dry-run --place-id 142823291 --duration 60
```

### Live mass (N cuentas)

```bash
C:/Python312/python.exe -m rakbot mass \
    --mass-cookies-path cookies.txt \
    --mass-cookies 10 \
    --mm2 --place-id 142823291 \
    --duration 3600
```

### GitPython (for scripting)

```bash
pip install cryptography GitPython
```

## Git

### Verificar que archivos sensibles NO se van a commitear

```bash
git check-ignore cookies.txt proxies.txt cookies.live.txt scripts/mm2-candy-farm/webhook.local.lua
# Debería listarlos todos
```

### Último commit + push

```bash
git add <files>
git commit -m "<msg>"
git push origin dev
```

### Tags

```bash
git tag mm2-py-0.4
git push origin dev --tags
```

### Rollback a tag

```bash
git checkout mm2-0.49    # Luau estable
git checkout mm2-py-0.3  # Python port + tests
```

### Ver ultimos N commits con tag

```bash
git log --oneline --decorate -20
```

## Luau executor

### Cargar Main.luau (desde executor)

```lua
loadstring(game:HttpGet("https://raw.githubusercontent.com/jaydee66z/curry-launcher/dev/scripts/mm2-candy-farm/Main.luau"))()
```

(Requires que el repo sea public. Si es private, download manual y paste.)

### Kill el collector sin recargar

```lua
running = false
```

### Dumpear state

```lua
print(game:GetService("HttpService"):JSONEncode(_G.farmDebug))
print("boxes:", _G.farmBoxesOpened)
print("lifetime:", _G.farmLifetimeCandies)
```

### Setup webhook URL antes de cargar Main.luau

```lua
_G.farmWebhookUrl = "https://discord.com/api/webhooks/..."
```

## Linux VPS

### SSH key setup

```bash
ssh-keygen -t ed25519 -C "bot@mydesk"
cat ~/.ssh/id_ed25519.pub | ssh root@VPS_IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### Transferir archivos

```bash
scp cookies.txt farmbot@VPS:~/curry-launcher/
scp proxies.txt farmbot@VPS:~/curry-launcher/
```

### systemd

```bash
sudo systemctl start mm2farm
sudo systemctl stop mm2farm
sudo systemctl restart mm2farm
sudo systemctl status mm2farm
sudo journalctl -u mm2farm -f    # follow logs
sudo journalctl -u mm2farm -n 100 # last 100 lines
```

### Verificar bot corriendo

```bash
ps aux | grep mass_worker | wc -l
pgrep -f mass_worker | wc -l
```

### Kill subprocesses (todos)

```bash
sudo pkill -f mass_worker
```

### Memory check

```bash
free -h
ps aux --sort=-%mem | head -10
```

## Discord webhook

### Test post

```bash
curl -X POST "$MM2_DISCORD_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{"content":"test from cheatsheet"}'
```

### Rich embed test

```bash
curl -X POST "$MM2_DISCORD_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{"username":"MM2","embeds":[{"title":"TEST","description":"body","color":15844367}]}'
```

## DataImpulse

### Test un proxy slot

```bash
PROXY=$(sed -n '1p' proxies.txt)  # first line
curl -x "http://$PROXY" https://api.ipify.org
```

### Test todos los slots (slow)

```bash
while IFS= read -r line; do
    if [[ ! $line =~ ^# ]] && [[ -n $line ]]; then
        ip=$(curl -s -m 10 -x "http://$line" https://api.ipify.org || echo "DEAD")
        echo "$line -> $ip"
    fi
done < proxies.txt | head -20
```

### Encriptar para backup

```bash
gpg --symmetric --cipher-algo AES256 proxies.txt
# Produces proxies.txt.gpg
```

## Monitoring (logs)

### Pickups último minuto

```bash
tail -1000 logs/mm2farm.log | grep -c pickup
```

### Drops recientes

```bash
grep rare_drop logs/mm2farm.log | tail -5
```

### Errores recientes

```bash
grep '"error"' logs/mm2farm.log | tail -10
```

### Rebuilds

```bash
grep hb_rebuild logs/mm2farm.log | wc -l
```

### Stats últimas 24h

```bash
cat > ~/stats.sh <<'EOF'
#!/bin/bash
LOG=~/curry-launcher/logs/mm2farm.log
echo "=== MM2 Farm $(date) ==="
echo "Pickups: $(grep -c pickup $LOG)"
echo "Boxes: $(grep -c box_fired $LOG)"
echo "Drops: $(grep -c rare_drop $LOG)"
echo "Errors: $(grep -c error $LOG)"
echo "Rebuilds: $(grep -c hb_rebuild $LOG)"
EOF
chmod +x ~/stats.sh
~/stats.sh
```

## Debugging

### Python traceback en tiempo real

```bash
# En lugar de systemd, para debug run manual
cd ~/curry-launcher
source .venv/bin/activate
C:/Python312/python.exe -m rakbot mass --mass-cookies 1 --mm2 --mm2-dry-run --place-id 142823291 2>&1 | tee debug.log
```

### Capture packets (Wireshark via tcpdump)

```bash
sudo tcpdump -i eth0 -w capture.pcap udp
# Ctrl+C
# Copy to local: scp farmbot@VPS:~/capture.pcap .
# Open in Wireshark
```

## Backup

### Snapshot Hetzner

```bash
# Via dashboard web solamente
# Hetzner Cloud → Server → Snapshots → Create
```

### Backup encrypted de todo

```bash
cd ~/curry-launcher
tar czf backup-$(date +%Y%m%d).tar.gz cookies.txt proxies.txt logs/ docs/
gpg --symmetric --cipher-algo AES256 backup-$(date +%Y%m%d).tar.gz
rm backup-$(date +%Y%m%d).tar.gz    # keep only .gpg
```

## Links

- [[MOC]]
- [[deployment/01-first-day-checklist]]
- [[troubleshooting/00-index]]

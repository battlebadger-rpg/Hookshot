# HookShot — Deploy to hookshot.kira-dashie.com

HookShot runs on the same Hetzner VPS as the existing SnapText app, on a different port and domain.

## First-time setup on server

### 1. Clone repo and install HookShot deps

```bash
git clone https://github.com/BattleBadger-rpg/Hookshot.git /root/hookshot
cd /root/hookshot/HookShot
pip3 install -r requirements.txt
```

### 2. Create systemd service

Create `/etc/systemd/system/hookshot.service`:

```ini
[Unit]
Description=HookShot Flask app
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/hookshot/HookShot
Environment=PATH=/usr/bin
ExecStart=/usr/bin/python3 -m gunicorn -w 1 -b 127.0.0.1:5002 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then:

```bash
apt install -y gunicorn   # if not installed
systemctl daemon-reload
systemctl enable hookshot
systemctl start hookshot
```

### 3. Nginx (add to existing config or new site)

Add a server block for hookshot.kira-dashie.com:

```nginx
server {
    listen 80;
    server_name hookshot.kira-dashie.com;
    location / {
        proxy_pass http://127.0.0.1:5002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Reload Nginx: `nginx -t && systemctl reload nginx`

### 4. SSL (Let's Encrypt)

```bash
certbot --nginx -d hookshot.kira-dashie.com
```

### 5. DNS (Cloudflare)

Add an **A** record: name `hookshot`, content `5.223.69.224`, proxy off (grey cloud).

---

## Deploy updates

**Option A — GitHub (recommended):** Push to `main`; the GitHub Action deploys automatically (SSH to VPS, `git pull` in `/root/hookshot`, restart hookshot). Add repo secrets: `VPS_HOST`, `VPS_USER`, `VPS_PASSWORD`.

**Option B — Manual:** From your machine, in the HookShot folder:

```powershell
python push_update.py
```

"""
One-time script: SSH to VPS and set up HookShot (clone repo, deps, systemd, nginx, SSL).
Optionally creates Cloudflare A record for hookshot.kira-dashie.com if CLOUDFLARE_API_TOKEN is set.
Reads .env in this folder. Run from the project root: python setup_hookshot_server.py
"""
import os
import sys

# Project root = folder containing this script and .env
ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")

def load_env():
    env = {}
    if not os.path.exists(ENV_PATH):
        print("ERROR: .env not found. Create it with VPS_HOST=, VPS_USER=, VPS_PASSWORD=")
        sys.exit(1)
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def main():
    env = load_env()
    host = env.get("VPS_HOST")
    user = env.get("VPS_USER") or "root"
    password = env.get("VPS_PASSWORD")
    certbot_email = env.get("CERTBOT_EMAIL", "").strip()
    if not host or not password:
        print("ERROR: Set VPS_HOST and VPS_PASSWORD in .env")
        sys.exit(1)

    try:
        import paramiko
    except ImportError:
        print("ERROR: Install paramiko: pip install paramiko")
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {user}@{host}...")
    ssh.connect(host, username=user, password=password, timeout=15)

    def run(cmd, timeout=120):
        print(f">>> {cmd}")
        _, out, err = ssh.exec_command(cmd, timeout=timeout)
        code = out.channel.recv_exit_status()
        out_s = out.read().decode(errors="replace")
        err_s = err.read().decode(errors="replace")
        safe = lambda s: s.encode("ascii", errors="replace").decode("ascii")
        if out_s:
            print(safe(out_s))
        if err_s and code != 0:
            print("stderr:", safe(err_s))
        return code

    # 1) Clone repo if /root/hookshot doesn't exist
    run("which git || (apt-get update -qq && apt-get install -y -qq git)")
    if run("test -d /root/hookshot") != 0:
        run("rm -rf /root/hookshot 2>/dev/null; git clone https://github.com/BattleBadger-rpg/Hookshot.git /root/hookshot", timeout=120)
    else:
        run("cd /root/hookshot && git pull origin main", timeout=60)

    # 2) Install HookShot deps in a venv (Ubuntu 24+ blocks system pip)
    run("apt-get install -y -qq python3-venv python3-pip 2>/dev/null")
    run("cd /root/hookshot/HookShot && python3 -m venv venv && ./venv/bin/pip install -q -r requirements.txt", timeout=90)

    # 3) Systemd service (use venv gunicorn)
    service = """[Unit]
Description=HookShot Flask app
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/hookshot/HookShot
Environment=PATH=/root/hookshot/HookShot/venv/bin:/usr/bin
ExecStart=/root/hookshot/HookShot/venv/bin/gunicorn -w 1 -b 127.0.0.1:5002 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
    run("cat > /etc/systemd/system/hookshot.service << 'HOOKSHOT_EOF'\n" + service + "HOOKSHOT_EOF")
    run("systemctl daemon-reload && systemctl enable hookshot && systemctl restart hookshot")
    run("sleep 2 && systemctl is-active hookshot")

    # 4) Nginx
    nginx_block = """server {
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
"""
    import base64
    b64 = base64.b64encode(nginx_block.encode()).decode()
    run(f"echo {b64} | base64 -d > /etc/nginx/sites-available/hookshot")
    run("ln -sf /etc/nginx/sites-available/hookshot /etc/nginx/sites-enabled/ 2>/dev/null; nginx -t && systemctl reload nginx")

    # 5) SSL (optional)
    if certbot_email:
        run(f"certbot --nginx -d hookshot.kira-dashie.com --non-interactive --agree-tos --email {certbot_email}", timeout=120)
    else:
        print("Skipping SSL (set CERTBOT_EMAIL in .env to enable). Run later: certbot --nginx -d hookshot.kira-dashie.com")

    ssh.close()

    # 6) Cloudflare DNS (optional): create A record hookshot.kira-dashie.com -> VPS
    cf_token = env.get("CLOUDFLARE_API_TOKEN", "").strip()
    cf_zone = env.get("CLOUDFLARE_ZONE", "kira-dashie.com").strip() or "kira-dashie.com"
    if cf_token:
        _setup_cloudflare_dns(cf_token, cf_zone, host)
    else:
        print("Skipping Cloudflare DNS (set CLOUDFLARE_API_TOKEN in .env to create A record).")

    print("Done. HookShot should be running.")


def _setup_cloudflare_dns(token, zone_name, ip):
    import urllib.request
    import json
    import ssl
    ctx = ssl.create_default_context()
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    # Get zone id
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/zones?name=" + zone_name,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print("Cloudflare zones request failed:", e)
        return
    zones = data.get("result", [])
    if not zones:
        print("Cloudflare: zone not found for", zone_name)
        return
    zone_id = zones[0]["id"]
    # Check for existing A record for hookshot
    list_req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type=A&name=hookshot.{zone_name}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(list_req, context=ctx) as r:
            list_data = json.loads(r.read().decode())
    except Exception as e:
        print("Cloudflare list records failed:", e)
        return
    records = list_data.get("result", [])
    body = json.dumps({"type": "A", "name": "hookshot", "content": ip, "ttl": 1, "proxied": False}).encode()
    if records:
        rec_id = records[0]["id"]
        upd = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{rec_id}",
            data=body,
            headers=headers,
            method="PUT",
        )
        try:
            with urllib.request.urlopen(upd, context=ctx) as r:
                print("Cloudflare: updated A record hookshot." + zone_name, "->", ip)
        except Exception as e:
            print("Cloudflare update failed:", e)
    else:
        create = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(create, context=ctx) as r:
                print("Cloudflare: created A record hookshot." + zone_name, "->", ip)
        except Exception as e:
            print("Cloudflare create failed:", e)


if __name__ == "__main__":
    main()

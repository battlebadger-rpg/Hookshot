"""One-shot deployment script for SnapText to od-server."""
import paramiko, io, sys, time

HOST     = '5.223.69.224'
USER     = 'root'
PASSWORD = 'EWL7ktAMeFrU'
APP_DIR  = '/root/snaptext'
DOMAIN   = 'snaptext.kira-dashie.com'
PORT     = 5001

APP_PY   = r"d:\AI tools\snap text tool\Snapchat Text on Screen\app.py"
HTML     = r"d:\AI tools\snap text tool\Snapchat Text on Screen\templates\index.html"


def run(ssh, cmd, timeout=180):
    print(f"\n>>> {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode(errors='replace')
    if out.strip():
        safe = out.strip().encode('ascii', errors='replace').decode('ascii')
        print(safe)
    return out


def main():
    print("Connecting to server...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    print("Connected.\n")

    # ── 1. System packages (already installed — verify only) ────────────────
    print("=" * 60)
    print("STEP 1: Verifying system packages")
    print("=" * 60)
    run(ssh, "ffmpeg -version 2>&1 | head -1")
    run(ssh, "python3 --version")

    # ── 2. App directory & file upload ──────────────────────────────────────
    print("=" * 60)
    print("STEP 2: Creating directories and uploading files")
    print("=" * 60)
    run(ssh, f"mkdir -p {APP_DIR}/templates {APP_DIR}/uploads {APP_DIR}/outputs")

    sftp = ssh.open_sftp()
    for local, remote in [(APP_PY, f"{APP_DIR}/app.py"),
                          (HTML,   f"{APP_DIR}/templates/index.html")]:
        with open(local, 'rb') as f:
            sftp.putfo(f, remote)
        print(f"Uploaded {local} -> {remote}")
    sftp.close()

    # ── 3. Python venv + packages ───────────────────────────────────────────
    print("=" * 60)
    print("STEP 3: Setting up Python virtual environment")
    print("=" * 60)
    run(ssh, f"python3 -m venv {APP_DIR}/venv", timeout=60)
    run(ssh, f"{APP_DIR}/venv/bin/pip install --upgrade pip flask gunicorn", timeout=120)

    # ── 4. Systemd service ──────────────────────────────────────────────────
    print("=" * 60)
    print("STEP 4: Creating systemd service")
    print("=" * 60)
    service = f"""[Unit]
Description=SnapText Flask App
After=network.target

[Service]
User=root
WorkingDirectory={APP_DIR}
Environment="PATH={APP_DIR}/venv/bin"
ExecStart={APP_DIR}/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:{PORT} --timeout 300 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    sftp = ssh.open_sftp()
    sftp.putfo(io.BytesIO(service.encode()), '/etc/systemd/system/snaptext.service')
    sftp.close()

    run(ssh, "systemctl daemon-reload")
    run(ssh, "systemctl enable snaptext")
    run(ssh, "systemctl restart snaptext")
    time.sleep(3)
    run(ssh, "systemctl status snaptext --no-pager")

    # ── 5. Nginx config ─────────────────────────────────────────────────────
    print("=" * 60)
    print("STEP 5: Configuring Nginx")
    print("=" * 60)
    nginx = f"""server {{
    listen 80;
    server_name {DOMAIN};

    client_max_body_size 500M;

    location / {{
        proxy_pass http://127.0.0.1:{PORT};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_connect_timeout 300s;
    }}
}}
"""
    sftp = ssh.open_sftp()
    sftp.putfo(io.BytesIO(nginx.encode()), f'/etc/nginx/sites-available/snaptext')
    sftp.close()

    run(ssh, "ln -sf /etc/nginx/sites-available/snaptext /etc/nginx/sites-enabled/snaptext")
    out = run(ssh, "nginx -t")
    run(ssh, "systemctl reload nginx")

    # ── 6. SSL via Certbot ──────────────────────────────────────────────────
    print("=" * 60)
    print("STEP 6: Obtaining SSL certificate")
    print("=" * 60)
    run(ssh, f"certbot --nginx -d {DOMAIN} --non-interactive --agree-tos "
             f"--redirect --keep-until-expiring 2>&1", timeout=120)

    # ── Done ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print(f"Visit: https://{DOMAIN}")
    print("All done!")
    print("=" * 60)
    ssh.close()


if __name__ == '__main__':
    main()

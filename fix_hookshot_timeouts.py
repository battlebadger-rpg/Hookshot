"""
Fix HookShot server timeouts so Telegram video send can complete.
- Gunicorn: add --timeout 300 (default 30s kills worker during upload)
- Nginx: add proxy_read_timeout, proxy_send_timeout 300s
Run: python fix_hookshot_timeouts.py
"""
import paramiko

HOST = '5.223.69.224'
USER = 'root'
PASSWORD = 'EWL7ktAMeFrU'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)

def run(cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    return (out.read() + err.read()).decode(errors='replace')

# 1) Update Gunicorn to use --timeout 300
print("Updating hookshot.service (Gunicorn --timeout 300)...")
run("sed -i 's/gunicorn -w 1/gunicorn -w 1 --timeout 300/' /etc/systemd/system/hookshot.service")
print(run("grep ExecStart /etc/systemd/system/hookshot.service"))

# 2) Update Nginx - add proxy timeouts to hookshot location block
# Certbot may have created ssl config; we need to add timeouts to location /
print("\nUpdating Nginx hookshot config (proxy timeouts 300s)...")
# Check if we already have proxy_read_timeout
has_timeout = run("grep -l 'proxy_read_timeout' /etc/nginx/sites-available/hookshot 2>/dev/null || true").strip()
if not has_timeout:
    # Insert proxy timeouts after proxy_set_header X-Forwarded-Proto
    run("""sed -i '/proxy_set_header X-Forwarded-Proto/a\\
        proxy_read_timeout 300s;\\
        proxy_send_timeout 300s;\\
        proxy_connect_timeout 300s;' /etc/nginx/sites-available/hookshot""")
else:
    print("(proxy timeouts already present)")
print(run("grep -A2 'proxy_pass' /etc/nginx/sites-available/hookshot | head -15"))

# 3) Reload
print("\nReloading services...")
print(run("systemctl daemon-reload && systemctl restart hookshot"))
print(run("nginx -t 2>&1"))
print(run("systemctl reload nginx 2>&1"))
print(run("sleep 2 && systemctl is-active hookshot"))

ssh.close()
print("\nDone. Try Send to Telegram again.")

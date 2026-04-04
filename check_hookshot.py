import os
env = {}
with open(os.path.join(os.path.dirname(__file__), '.env'), 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(env['VPS_HOST'], username=env['VPS_USER'], password=env['VPS_PASSWORD'], timeout=15)
def run(cmd, timeout=10):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return (out.read().decode() + err.read().decode()).strip()
safe = lambda s: s.encode('ascii', errors='replace').decode('ascii')
print('=== Curl 127.0.0.1:5002 (app direct) ===')
print(safe(run('curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:5002/login')))
print()
print('=== Curl via nginx (Host: hookshot.kira-dashie.com) ===')
print(safe(run('curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "Host: hookshot.kira-dashie.com" https://127.0.0.1/ -k')))
print()
print('=== Nginx error log (hookshot/upstream) ===')
print(safe(run('grep -i hookshot /var/log/nginx/error.log 2>/dev/null | tail -20')))
print()
print('=== Curl with 30s timeout ===')
print(safe(run('curl -s -o /dev/null -w "%{http_code}" --max-time 30 http://127.0.0.1:5002/login')))
print()
print('=== Test app import (timeout 20s) ===')
print(safe(run('cd /root/hookshot/HookShot && timeout 20 ./venv/bin/python -c "import app; print(\"ok\")" 2>&1')))
ssh.close()

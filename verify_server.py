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
def run(cmd, timeout=8):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return (out.read().decode() + err.read().decode()).strip()
def safe(s):
    return s.encode('ascii', errors='replace').decode('ascii')
# Upload app.py and restart
with open(os.path.join(os.path.dirname(__file__), 'HookShot', 'app.py'), 'rb') as f:
    data = f.read()
sftp = ssh.open_sftp()
with sftp.open('/root/hookshot/HookShot/app.py', 'wb') as rem:
    rem.write(data)
sftp.close()
# Restart without blocking on full output
stdin, stdout, stderr = ssh.exec_command('systemctl restart hookshot', timeout=25)
stdout.channel.recv_exit_status()
import time
time.sleep(6)
print("=== curl /health (5s) ===")
try:
    print(safe(run('curl -s -w "\\n%{http_code}" --max-time 5 http://127.0.0.1:5002/health', timeout=8)))
except Exception as e:
    print("Error:", e)
print("\n=== curl /login (5s) ===")
try:
    print(safe(run('curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:5002/login', timeout=8)))
except Exception as e:
    print("Error:", e)
ssh.close()

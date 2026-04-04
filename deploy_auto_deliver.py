"""
Deploy auto-deliver feature:
- Upload updated db.py and app.py
- Run DB migration (adds tg_chat_id, tg_topic_id, auto_deliver columns)
- Add HOOKSHOT_AUTO_KEY to systemd service environment
- Install cron job (23:00 UTC = 7 AM GMT+8)
- Restart + health check
"""
import paramiko
import time
import secrets

HOST       = '5.223.69.224'
USER       = 'root'
PASS       = 'EWL7ktAMeFrU'
REMOTE_DIR = '/root/hookshot/HookShot'

# Generate a random key (or set a fixed one here if you want to keep it stable)
AUTO_KEY = secrets.token_hex(24)
print(f'Auto-deliver key: {AUTO_KEY}')
print('(Save this if you want to trigger the endpoint manually later)')

FILES = [
    (r'd:\AI tools\HookShot\HookShot\app.py', f'{REMOTE_DIR}/app.py'),
    (r'd:\AI tools\HookShot\HookShot\db.py',  f'{REMOTE_DIR}/db.py'),
]

print('\nConnecting…')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

def run(cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    result = (out.read() + err.read()).decode(errors='replace')
    result = result.encode('ascii', errors='replace').decode('ascii')
    print(f'>>> {cmd[:90]}\n{result.strip()}')
    return result.strip()

# Upload files
sftp = ssh.open_sftp()
for local, remote in FILES:
    with open(local, 'rb') as f:
        sftp.putfo(f, remote)
    print(f'Uploaded {remote}')
sftp.close()

# Run DB migration
run(
    f'cd {REMOTE_DIR} && venv/bin/python -c "import db; db.migrate_db(); print(\'Migration OK\')" 2>&1',
    timeout=30,
)

# Add HOOKSHOT_AUTO_KEY to systemd service
# Read current service file, add/replace the env line
svc_file = '/etc/systemd/system/hookshot.service'
result = run(f'cat {svc_file}')
if 'HOOKSHOT_AUTO_KEY' in result:
    # Replace existing key
    run(f"sed -i 's/HOOKSHOT_AUTO_KEY=.*/HOOKSHOT_AUTO_KEY={AUTO_KEY}\"/' {svc_file}")
else:
    # Add after the existing HOOKSHOT_TELEGRAM_TOKEN line (or after [Service])
    run(f"sed -i '/HOOKSHOT_TELEGRAM_TOKEN/a Environment=\"HOOKSHOT_AUTO_KEY={AUTO_KEY}\"' {svc_file}")

run('systemctl daemon-reload')

# Install cron job (23:00 UTC daily)
cron_line = f'0 23 * * * curl -s -X POST http://127.0.0.1:5002/api/auto-deliver -H "X-Auto-Key: {AUTO_KEY}" >> /var/log/hookshot_auto.log 2>&1'
# Remove any old hookshot auto-deliver cron line, then add new one
run(f"crontab -l 2>/dev/null | grep -v 'api/auto-deliver' | {{ cat; echo '{cron_line}'; }} | crontab -")
print('Cron job installed.')
run('crontab -l')

# Restart
print('\nRestarting hookshot…')
run('systemctl restart hookshot')
time.sleep(8)

health = run('curl -s -o /dev/null -w "%{http_code}" --max-time 15 http://127.0.0.1:5002/health 2>&1')
if '200' in health:
    print('\nSite is UP. Auto-deliver deployed!')
    print(f'\nTo test manually:\n  curl -X POST http://127.0.0.1:5002/api/auto-deliver -H "X-Auto-Key: {AUTO_KEY}"')
else:
    print(f'Health returned: {health} — retrying in 10s…')
    time.sleep(10)
    run('systemctl restart hookshot')
    time.sleep(8)
    health2 = run('curl -s -o /dev/null -w "%{http_code}" --max-time 15 http://127.0.0.1:5002/health 2>&1')
    print('Site UP.' if '200' in health2 else f'WARNING: still {health2}. Check manually.')

ssh.close()

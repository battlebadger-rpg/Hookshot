"""Run from project root. SSHs to VPS and runs a quick Telegram send test."""
import paramiko

HOST = '5.223.69.224'
USER = 'root'
PASSWORD = 'EWL7ktAMeFrU'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)

# Get token and run inline Python test
cmd = r'''cd /root/hookshot/HookShot && \
TOKEN=$(grep -o 'HOOKSHOT_TELEGRAM_TOKEN=[^ ]*' /etc/systemd/system/hookshot.service 2>/dev/null | head -1) && \
export $TOKEN && \
./venv/bin/python -c "
import os, json, urllib.request, urllib.error
token = os.environ.get('HOOKSHOT_TELEGRAM_TOKEN')
with open('telegram_users.json') as f: users = json.load(f)
chat_id = users.get('todd')
if not chat_id: print('todd not in telegram_users'); exit(1)
url = 'https://api.telegram.org/bot' + token + '/sendMessage'
data = json.dumps({'chat_id': chat_id, 'text': 'HookShot test: Telegram send OK.'}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    j = json.loads(r.read())
    print('OK: message sent' if j.get('ok') else 'API:', j)
"
'''
_, stdout, stderr = ssh.exec_command(cmd, timeout=30)
out = stdout.read().decode(errors='replace')
err = stderr.read().decode(errors='replace')
print(out)
if err.strip():
    print("stderr:", err)
ssh.close()
print("Done.")

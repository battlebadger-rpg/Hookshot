"""Run on server: cd /root/hookshot/HookShot && ./venv/bin/python test_telegram_send.py
Sends a test video (or message) to todd's Telegram to verify the bot works."""
import os
import sys
import json

# Run from HookShot dir
os.chdir('/root/hookshot/HookShot')
sys.path.insert(0, '/root/hookshot/HookShot')

# Load token from env (service has it)
token = os.environ.get('HOOKSHOT_TELEGRAM_TOKEN')
if not token:
    # Try reading from service file
    try:
        with open('/etc/systemd/system/hookshot.service') as f:
            for line in f:
                if line.strip().startswith('Environment=') and 'HOOKSHOT' in line:
                    for part in line.split():
                        if part.startswith('HOOKSHOT_TELEGRAM_TOKEN='):
                            token = part.split('=', 1)[1].strip()
                            break
    except Exception:
        pass

if not token:
    print('No token found. Set HOOKSHOT_TELEGRAM_TOKEN in hookshot.service')
    sys.exit(1)

# Load telegram_users to get todd's chat_id
users_file = '/root/hookshot/HookShot/telegram_users.json'
if not os.path.exists(users_file):
    print('telegram_users.json not found')
    sys.exit(1)
with open(users_file) as f:
    users = json.load(f)
chat_id = users.get('todd')
if not chat_id:
    print('todd not in telegram_users.json')
    sys.exit(1)

# Send test message
import urllib.request
import urllib.error
url = f'https://api.telegram.org/bot{token}/sendMessage'
data = json.dumps({'chat_id': chat_id, 'text': 'HookShot test: Telegram send is working.'}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        r = json.loads(resp.read())
        if r.get('ok'):
            print('OK: Test message sent to todd.')
        else:
            print('API error:', r)
except urllib.error.HTTPError as e:
    print('HTTP error:', e.code, e.read().decode()[:200])
except Exception as e:
    print('Error:', e)
    sys.exit(1)

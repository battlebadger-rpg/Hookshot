"""
telegram_setup.py — One-time setup for Telegram bots for SnapText and HookShot.

BEFORE RUNNING:
1. Create two bots via @BotFather in Telegram:
   - /newbot → name it "SnapText" (or similar) → get token
   - /newbot → name it "HookShot" (or similar) → get token
2. Fill in the tokens below:
"""
import urllib.request, json, paramiko

SNAPTEXT_TOKEN  = '8434074134:AAGjYkfj94ukxm5qJVDhpx2V1fUK0_FpKkY'   # @OD_snaptext_bot
HOOKSHOT_TOKEN  = '8549015220:AAGzRPdl_mg9Nv-Y6kj-cwxX78ZY-P8wzxk'   # @OD_hookshot_bot

SNAPTEXT_URL  = 'https://snaptext.kira-dashie.com/api/telegram/webhook'
HOOKSHOT_URL  = 'https://hookshot.kira-dashie.com/api/telegram/webhook'

VPS_HOST = '5.223.69.224'
VPS_USER = 'root'
VPS_PASS = 'EWL7ktAMeFrU'

def set_webhook(token, webhook_url, label):
    if not token:
        print(f'[{label}] SKIPPED — no token provided')
        return
    url = f'https://api.telegram.org/bot{token}/setWebhook'
    body = json.dumps({'url': webhook_url}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    print(f'[{label}] setWebhook: {result}')

def update_service(ssh, service_name, env_key, token):
    if not token:
        return
    _, out, _ = ssh.exec_command(f'cat /etc/systemd/system/{service_name}.service')
    content = out.read().decode()
    # Add or replace the env var in the service file
    env_line = f'Environment={env_key}={token}'
    if env_key in content:
        lines = []
        for line in content.splitlines():
            if line.strip().startswith(f'Environment={env_key}'):
                lines.append(env_line)
            else:
                lines.append(line)
        new_content = '\n'.join(lines)
    else:
        # Insert after the existing Environment= line
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if line.strip().startswith('Environment=PATH='):
                new_lines.append(env_line)
        new_content = '\n'.join(new_lines)
    
    import io
    sftp = ssh.open_sftp()
    with sftp.open(f'/etc/systemd/system/{service_name}.service', 'w') as f:
        f.write(new_content)
    sftp.close()
    print(f'[{service_name}] Service file updated with {env_key}')

def run(ssh, cmd):
    _, out, err = ssh.exec_command(cmd, timeout=20)
    out.channel.recv_exit_status()
    return (out.read() + err.read()).decode(errors='replace').strip()

if __name__ == '__main__':
    if not SNAPTEXT_TOKEN and not HOOKSHOT_TOKEN:
        print('ERROR: No tokens provided. Edit this script and add your bot tokens first.')
        print()
        print('Steps:')
        print('  1. Open Telegram and message @BotFather')
        print('  2. Send /newbot and follow prompts (create one for SnapText, one for HookShot)')
        print('  3. Copy the token BotFather gives you into this script')
        print('  4. Run this script again')
        exit(1)

    # Connect to VPS and update service files
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS, timeout=30)

    if SNAPTEXT_TOKEN:
        update_service(ssh, 'snaptext', 'SNAPTEXT_TELEGRAM_TOKEN', SNAPTEXT_TOKEN)
    if HOOKSHOT_TOKEN:
        update_service(ssh, 'hookshot', 'HOOKSHOT_TELEGRAM_TOKEN', HOOKSHOT_TOKEN)

    print(run(ssh, 'systemctl daemon-reload'))
    if SNAPTEXT_TOKEN:
        print(run(ssh, 'systemctl restart snaptext'))
    if HOOKSHOT_TOKEN:
        print(run(ssh, 'systemctl restart hookshot'))

    import time; time.sleep(4)

    if SNAPTEXT_TOKEN:
        print(run(ssh, 'systemctl is-active snaptext'))
    if HOOKSHOT_TOKEN:
        print(run(ssh, 'systemctl is-active hookshot'))

    ssh.close()

    # Register webhooks with Telegram
    set_webhook(SNAPTEXT_TOKEN, SNAPTEXT_URL, 'SnapText')
    set_webhook(HOOKSHOT_TOKEN, HOOKSHOT_URL, 'HookShot')

    print()
    print('Done! Your bots are now connected.')
    print('Staff can now click "Connect Telegram" in either tool to link their account.')

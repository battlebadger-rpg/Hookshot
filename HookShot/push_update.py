"""
Deploy HookShot app to Hetzner VPS (hookshot.kira-dashie.com).
Uploads app files to /root/hookshot/ and restarts the hookshot service.
First-time: create /root/hookshot, install deps, add systemd service and Nginx (see HOOKSHOT_DEPLOY.md).
"""
import paramiko
import os

HOST = '5.223.69.224'
USER = 'root'
PASSWORD = 'EWL7ktAMeFrU'
REMOTE_DIR = '/root/hookshot'
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)

def run(cmd, timeout=60):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    result = out.read().decode(errors='replace') + err.read().decode(errors='replace')
    safe = result.encode('ascii', errors='replace').decode('ascii')
    print('>>>', cmd)
    print(safe)

sftp = ssh.open_sftp()

def put_file(local_path, remote_path):
    with open(local_path, 'rb') as f:
        sftp.putfo(f, remote_path)
    print('Uploaded', remote_path)

# Ensure remote dirs exist
run(f'mkdir -p {REMOTE_DIR}/templates {REMOTE_DIR}/library_videos {REMOTE_DIR}/uploads {REMOTE_DIR}/outputs')

files = [
    ('app.py', 'app.py'),
    ('db.py', 'db.py'),
    ('requirements.txt', 'requirements.txt'),
    ('users.json', 'users.json'),
]
for local_name, remote_name in files:
    put_file(os.path.join(LOCAL_ROOT, local_name), f'{REMOTE_DIR}/{remote_name}')

for name in os.listdir(os.path.join(LOCAL_ROOT, 'templates')):
    put_file(os.path.join(LOCAL_ROOT, 'templates', name), f'{REMOTE_DIR}/templates/{name}')

sftp.close()

# Restart service (create first time: see HOOKSHOT_DEPLOY.md)
run('systemctl restart hookshot 2>/dev/null || echo "Service hookshot not found - create it first."')
import time
time.sleep(2)
run('systemctl is-active hookshot 2>/dev/null || true')

ssh.close()
print('Done.')

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
sftp = ssh.open_sftp()
# Upload migration script
migrate_script = b"""import sys, os
os.chdir('/root/hookshot/HookShot')
sys.path.insert(0, '/root/hookshot/HookShot')
import db
db.init_db()
db.seed_and_migrate_if_empty('/root/hookshot/HookShot')
print('Migration done')
"""
with sftp.open('/root/hookshot/HookShot/migrate_once.py', 'wb') as f:
    f.write(migrate_script)
sftp.close()
# Run migration
_, out, err = ssh.exec_command('cd /root/hookshot/HookShot && ./venv/bin/python migrate_once.py', timeout=30)
code = out.channel.recv_exit_status()
print(out.read().decode(), err.read().decode(), 'Exit:', code)
# Update systemd to run migration before gunicorn
service = """[Unit]
Description=HookShot Flask app
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/hookshot/HookShot
ExecStartPre=/root/hookshot/HookShot/venv/bin/python -c "import sys; sys.path.insert(0,'/root/hookshot/HookShot'); import db; db.init_db(); db.seed_and_migrate_if_empty('/root/hookshot/HookShot')"
Environment=PATH=/root/hookshot/HookShot/venv/bin:/usr/bin
ExecStart=/root/hookshot/HookShot/venv/bin/gunicorn -w 1 -b 127.0.0.1:5002 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
# Write service file via heredoc
_, out, err = ssh.exec_command("cat > /etc/systemd/system/hookshot.service << 'ENDMARK'\n" + service + "ENDMARK\n", timeout=5)
out.channel.recv_exit_status()
# Reload and restart
_, out, err = ssh.exec_command('systemctl daemon-reload && systemctl restart hookshot && sleep 4 && systemctl is-active hookshot', timeout=15)
print(out.read().decode(), err.read().decode())
ssh.close()
print('Done. Test: curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:5002/login')

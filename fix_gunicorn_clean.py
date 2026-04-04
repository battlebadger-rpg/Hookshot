"""Fix duplicate --timeout in gunicorn, use single --timeout 300."""
import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=15):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
# Replace entire ExecStart line with clean version (preserve Environment lines)
# Read current, rewrite
_, o, _ = ssh.exec_command("cat /etc/systemd/system/hookshot.service", timeout=5)
content = o.read().decode()
# Fix: ensure single --timeout 300, correct gunicorn line
new_content = content.replace(
    "ExecStart=/root/hookshot/HookShot/venv/bin/gunicorn -w 1 --timeout 300 -b 127.0.0.1:5002 --timeout 300 app:app",
    "ExecStart=/root/hookshot/HookShot/venv/bin/gunicorn -w 1 --timeout 300 -b 127.0.0.1:5002 app:app"
)
# Also handle other possible formats
import re
new_content = re.sub(r'--timeout 300[^a-z]*--timeout 300', '--timeout 300', new_content)
with ssh.open_sftp() as sftp:
    from io import BytesIO
    sftp.putfo(BytesIO(new_content.encode()), '/etc/systemd/system/hookshot.service')
run("systemctl daemon-reload && systemctl restart hookshot")
time.sleep(6)
print("ExecStart:", run("grep ExecStart /etc/systemd/system/hookshot.service"))
print("Status:", run("systemctl is-active hookshot"))
print("Curl:", run("curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5002/health 2>&1"))
ssh.close()

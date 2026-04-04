"""Fix Gunicorn config (remove duplicate timeout) and restart. Get site back online."""
import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=15):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
# Fix ExecStart: single --timeout 300 (background send = no long request needed)
run("sed -i 's/--timeout 300 --timeout 600/--timeout 300/' /etc/systemd/system/hookshot.service")
run("sed -i 's/--timeout 600 --timeout 300/--timeout 300/' /etc/systemd/system/hookshot.service")
run("systemctl daemon-reload && systemctl restart hookshot")
time.sleep(6)
code = run("curl -s -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:5002/health 2>&1")
print("Health:", code)
print("ExecStart:", run("grep ExecStart /etc/systemd/system/hookshot.service"))
ssh.close()
print("Done. Site should be up." if code.strip() == '200' else "Health check failed - try again in 30s.")

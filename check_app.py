import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=30):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
print("curl /health (30s):", run("curl -s -w ' code:%{http_code}' --max-time 30 http://127.0.0.1:5002/health 2>&1"))
print("Port 5002:", run("ss -tlnp | grep 5002 2>&1"))
print("App import test:", run("cd /root/hookshot/HookShot && timeout 15 ./venv/bin/python -c 'import app; print(\"ok\")' 2>&1"))
ssh.close()

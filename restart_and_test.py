import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=30):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
print("Restarting hookshot...")
run("systemctl restart hookshot")
time.sleep(5)
print("After 5s - curl /health:")
print(run("curl -s -w '\\ncode:%{http_code}' --max-time 15 http://127.0.0.1:5002/health 2>&1"))
print("\ncurl /login:")
print(run("curl -s -o /dev/null -w 'code:%{http_code}' --max-time 15 http://127.0.0.1:5002/login 2>&1"))
ssh.close()

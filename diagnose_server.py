"""Quick server diagnostic. Run: python diagnose_server.py"""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, timeout=15):
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    o.channel.recv_exit_status()
    return (o.read() + e.read()).decode(errors='replace')
print("=== hookshot service status ===")
print(run("systemctl status hookshot --no-pager 2>&1 | head -25"))
print("\n=== curl localhost:5002/health ===")
print(run("curl -s -w '\\nHTTP_CODE:%{http_code}' --max-time 10 http://127.0.0.1:5002/health 2>&1"))
print("\n=== nginx error log (last 10) ===")
print(run("tail -10 /var/log/nginx/error.log 2>&1"))
print("\n=== journalctl hookshot (last 15) ===")
print(run("journalctl -u hookshot -n 15 --no-pager 2>&1"))
ssh.close()

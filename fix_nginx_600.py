"""Set Nginx proxy timeouts to 600s for hookshot (match Gunicorn)."""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=15):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
# Replace 300s with 600s in hookshot nginx config
run("sed -i 's/proxy_read_timeout 300s/proxy_read_timeout 600s/' /etc/nginx/sites-available/hookshot")
run("sed -i 's/proxy_send_timeout 300s/proxy_send_timeout 600s/' /etc/nginx/sites-available/hookshot")
run("sed -i 's/proxy_connect_timeout 300s/proxy_connect_timeout 600s/' /etc/nginx/sites-available/hookshot")
print(run("grep proxy_.*_timeout /etc/nginx/sites-available/hookshot"))
print(run("nginx -t 2>&1"))
print(run("systemctl reload nginx 2>&1"))
ssh.close()
print("Done. Nginx proxy timeouts now 600s.")

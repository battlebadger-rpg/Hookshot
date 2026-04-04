"""Add Nginx proxy timeouts for hookshot. Run: python fix_nginx_timeouts.py"""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, timeout=15):
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    o.channel.recv_exit_status()
    return (o.read() + e.read()).decode()
# Use Python on server to patch nginx config (sed newlines are fiddly)
patch_script = '''
import re
path = "/etc/nginx/sites-available/hookshot"
with open(path) as f:
    c = f.read()
if "proxy_read_timeout" in c:
    print("Already has proxy timeouts")
else:
    c = c.replace(
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_set_header X-Forwarded-Proto $scheme;\\n        proxy_read_timeout 300s;\\n        proxy_send_timeout 300s;\\n        proxy_connect_timeout 300s;"
    )
    with open(path, "w") as f:
        f.write(c)
    print("Added proxy timeouts")
'''
run("python3 -c " + repr(patch_script))
print(run("nginx -t 2>&1"))
print(run("systemctl reload nginx 2>&1"))
ssh.close()
print("Done.")

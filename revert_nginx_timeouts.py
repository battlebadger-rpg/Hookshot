"""Revert nginx proxy timeouts - remove them to see if that fixes loading."""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=15):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
# Remove the proxy timeout lines we added
patch = '''
path = "/etc/nginx/sites-available/hookshot"
with open(path) as f:
    c = f.read()
c = c.replace("        proxy_read_timeout 300s;\\n        proxy_send_timeout 300s;\\n        proxy_connect_timeout 300s;\\n", "")
with open(path, "w") as f:
    f.write(c)
print("Removed proxy timeouts")
'''
run("python3 -c " + repr(patch))
print(run("nginx -t 2>&1"))
print(run("systemctl reload nginx 2>&1"))
ssh.close()
print("Done. Try loading the page.")
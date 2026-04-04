"""Quick fix: add --timeout 300 to Gunicorn. Run: python fix_gunicorn_only.py"""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd):
    _, o, e = ssh.exec_command(cmd, timeout=15)
    o.channel.recv_exit_status()
    return (o.read() + e.read()).decode()
# Add timeout if not present
run("grep -q 'timeout 300' /etc/systemd/system/hookshot.service || sed -i 's/gunicorn -w 1/gunicorn -w 1 --timeout 300/' /etc/systemd/system/hookshot.service")
run("systemctl daemon-reload && systemctl restart hookshot")
print(run("grep ExecStart /etc/systemd/system/hookshot.service"))
print("hookshot:", run("systemctl is-active hookshot"))
ssh.close()
print("Done.")

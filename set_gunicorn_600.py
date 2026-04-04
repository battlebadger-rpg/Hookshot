"""Set Gunicorn timeout to 600s for 5-video sends."""
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=15):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
run("sed -i 's/--timeout 300/--timeout 600/' /etc/systemd/system/hookshot.service")
run("systemctl daemon-reload && systemctl restart hookshot")
print("ExecStart:", run("grep ExecStart /etc/systemd/system/hookshot.service"))
print("Status:", run("systemctl is-active hookshot"))
ssh.close()
print("Done.")

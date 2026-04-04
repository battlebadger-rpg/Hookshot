import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
_, o, e = ssh.exec_command('systemctl restart hookshot', timeout=10)
o.channel.recv_exit_status()
print((o.read()+e.read()).decode())
ssh.close()
print("Done.")

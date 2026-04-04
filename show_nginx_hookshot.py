import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
_, o, _ = ssh.exec_command("cat /etc/nginx/sites-available/hookshot", timeout=10)
print(o.read().decode())
ssh.close()

import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)

def run(cmd, timeout=20):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    result = out.read().decode(errors='replace') + err.read().decode(errors='replace')
    safe = result.encode('ascii', errors='replace').decode('ascii')
    print(f'>>> {cmd}\n{safe}')

sftp = ssh.open_sftp()
files = [
    (r"d:\AI tools\snap text tool\Snapchat Text on Screen\templates\index.html",
     '/root/snaptext/templates/index.html'),
    (r"d:\AI tools\snap text tool\Snapchat Text on Screen\templates\login.html",
     '/root/snaptext/templates/login.html'),
]
for local, remote in files:
    with open(local, 'rb') as f:
        sftp.putfo(f, remote)
    print(f'Uploaded {remote}')
sftp.close()

run('systemctl restart snaptext')
time.sleep(2)
run('systemctl is-active snaptext')

ssh.close()
print('Done.')

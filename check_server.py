import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)

def run(cmd):
    _, out, err = ssh.exec_command(cmd, timeout=30)
    result = out.read().decode(errors='replace') + err.read().decode(errors='replace')
    safe = result.encode('ascii', errors='replace').decode('ascii')
    print(f'\n--- {cmd} ---')
    print(safe)

run('journalctl -u snaptext -n 50 --no-pager --output=cat')
run('ls -la /root/snaptext/uploads/')
run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/')
run('curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/upload -X POST')

ssh.close()
print('\nDone.')

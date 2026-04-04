"""Stop hookshot, run app manually to capture startup errors."""
import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.223.69.224', username='root', password='EWL7ktAMeFrU', timeout=15)
def run(cmd, t=20):
    _, o, e = ssh.exec_command(cmd, timeout=t)
    o.channel.recv_exit_status()
    return (o.read()+e.read()).decode()
# Stop service
run("systemctl stop hookshot")
time.sleep(2)
# Run gunicorn in foreground for 20 seconds, with a curl in parallel
# We'll run gunicorn in background and curl after 3s
chan = ssh.get_transport().open_session()
chan.exec_command("cd /root/hookshot/HookShot && export HOOKSHOT_TELEGRAM_TOKEN=$(grep HOOKSHOT_TELEGRAM_TOKEN /etc/systemd/system/hookshot.service | head -1 | sed 's/.*=//') && timeout 25 ./venv/bin/gunicorn -w 1 -b 127.0.0.1:5002 app:app 2>&1")
time.sleep(5)
# Now curl
_, o2, _ = ssh.exec_command("curl -s -w '\\ncode:%{http_code}' --max-time 10 http://127.0.0.1:5002/health 2>&1", timeout=15)
print("Curl result:", (o2.read()+o2.channel.recv_stderr(1024)).decode())
# Get gunicorn output
time.sleep(2)
if chan.recv_ready():
    print("Gunicorn:", chan.recv(4096).decode(errors='replace'))
# Restart service
run("systemctl start hookshot")
ssh.close()
print("Service restarted.")

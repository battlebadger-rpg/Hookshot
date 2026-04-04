"""Upload CSVs, re-seed DB, upload videos to server."""
import os, sys, time

env = {}
with open(os.path.join(os.path.dirname(__file__), '.env'), 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(env['VPS_HOST'], username=env['VPS_USER'], password=env['VPS_PASSWORD'], timeout=15)
sftp = ssh.open_sftp()

ROOT = os.path.dirname(__file__)

# ------------------------------------------------------------------
# 1. Upload CSVs
# ------------------------------------------------------------------
print("=== Uploading CSVs ===")
csv_src = os.path.join(ROOT, 'caption library')
for fname in ('caption_library.csv', 'video_library.csv', 'performance_insights.csv'):
    local = os.path.join(csv_src, fname)
    remote = f'/root/hookshot/HookShot/{fname}'
    if os.path.exists(local):
        sftp.put(local, remote)
        print(f"  Uploaded {fname}")
    else:
        print(f"  MISSING locally: {fname}")

# ------------------------------------------------------------------
# 2. Re-seed DB (wipe captions first so seed runs even if empty check passed)
# ------------------------------------------------------------------
print("\n=== Re-seeding database ===")
seed_script = b"""import sys, os
os.chdir('/root/hookshot/HookShot')
sys.path.insert(0, '/root/hookshot/HookShot')
import sqlite3
conn = sqlite3.connect('/root/hookshot/HookShot/hookshot.db')
cur = conn.cursor()
# Force re-seed by deleting existing captions/videos/accounts
cur.execute('DELETE FROM batch_items')
cur.execute('DELETE FROM batches')
cur.execute('DELETE FROM captions')
cur.execute('DELETE FROM videos')
cur.execute('DELETE FROM accounts')
conn.commit()
conn.close()
import db
db.init_db()
db.seed_and_migrate_if_empty('/root/hookshot/HookShot')
# Report results
conn2 = sqlite3.connect('/root/hookshot/HookShot/hookshot.db')
c2 = conn2.cursor()
c2.execute('SELECT COUNT(*) FROM captions'); caps = c2.fetchone()[0]
c2.execute('SELECT COUNT(*) FROM videos');  vids = c2.fetchone()[0]
c2.execute('SELECT COUNT(*) FROM accounts'); accs = c2.fetchone()[0]
conn2.close()
print(f'Accounts: {accs}  Videos: {vids}  Captions: {caps}')
"""
with sftp.open('/root/hookshot/HookShot/reseed.py', 'wb') as f:
    f.write(seed_script)
_, out, err = ssh.exec_command('cd /root/hookshot/HookShot && ./venv/bin/python reseed.py', timeout=30)
code = out.channel.recv_exit_status()
txt = (out.read().decode() + err.read().decode()).strip()
print(txt or '(no output)', '  Exit:', code)

# ------------------------------------------------------------------
# 3. Upload videos
# ------------------------------------------------------------------
print("\n=== Uploading videos ===")
vid_src = os.path.join(ROOT, 'videos 1 to 10')
remote_lib = '/root/hookshot/HookShot/library_videos'

# Make sure remote dir exists
try: sftp.mkdir(remote_lib)
except: pass

video_files = sorted(os.listdir(vid_src))
for fname in video_files:
    local = os.path.join(vid_src, fname)
    base, ext = os.path.splitext(fname)
    vid_id = base.upper()  # e.g. V01, V02
    remote_tmp = f'{remote_lib}/{fname}'
    remote_mp4 = f'{remote_lib}/{vid_id}.mp4'
    size_mb = os.path.getsize(local) / 1024 / 1024
    print(f"  Uploading {fname} ({size_mb:.1f} MB)...", end='', flush=True)
    sftp.put(local, remote_tmp)
    print(' done', flush=True)
    if ext.upper() != '.MP4':
        # Convert to mp4 on server
        print(f"    Converting {fname} -> {vid_id}.mp4 ...", end='', flush=True)
        _, co, ce = ssh.exec_command(
            f'ffmpeg -y -i "{remote_tmp}" -c copy "{remote_mp4}" 2>/dev/null && rm -f "{remote_tmp}"',
            timeout=60,
        )
        co.channel.recv_exit_status()
        print(' converted', flush=True)
    else:
        # Already mp4, just rename
        _, co, ce = ssh.exec_command(f'mv -f "{remote_tmp}" "{remote_mp4}"', timeout=5)
        co.channel.recv_exit_status()

sftp.close()

# ------------------------------------------------------------------
# 4. Verify
# ------------------------------------------------------------------
print("\n=== Verification ===")
_, out, err = ssh.exec_command(
    'ls /root/hookshot/HookShot/library_videos/ && '
    'sqlite3 /root/hookshot/HookShot/hookshot.db "SELECT COUNT(*) FROM captions; SELECT COUNT(*) FROM videos;"',
    timeout=10,
)
out.channel.recv_exit_status()
print(out.read().decode().strip())
ssh.close()
print("\nAll done.")

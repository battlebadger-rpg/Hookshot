"""
Deploy font update:
- Download TikTok Sans Bold (from GitHub ZIP) and Inter Bold (from Google Fonts)
- Upload both TTF files to /root/hookshot/HookShot/fonts/ on the server
- Upload updated app.py and index.html
- Restart + health check
"""
import paramiko
import urllib.request
import zipfile
import io
import os
import time

HOST = '5.223.69.224'
USER = 'root'
PASS = 'EWL7ktAMeFrU'
REMOTE_DIR = '/root/hookshot/HookShot'

FILES = [
    (r'd:\AI tools\HookShot\HookShot\app.py',                   f'{REMOTE_DIR}/app.py'),
    (r'd:\AI tools\HookShot\HookShot\templates\index.html',     f'{REMOTE_DIR}/templates/index.html'),
]

# ── Download fonts locally ────────────────────────────────────────────────────

print('Downloading Inter Bold from Google Fonts…')
inter_url = 'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZg.ttf'
with urllib.request.urlopen(inter_url, timeout=30) as r:
    inter_bytes = r.read()
print(f'Inter Bold: {len(inter_bytes):,} bytes')

print('Downloading TikTok Sans ZIP from GitHub…')
tiktok_zip_url = 'https://github.com/tiktok/TikTokSans/releases/download/v4.000/TikTokSans-v4.000.zip'
req = urllib.request.Request(tiktok_zip_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=60) as r:
    tiktok_zip_bytes = r.read()
print(f'ZIP downloaded: {len(tiktok_zip_bytes):,} bytes')

print('Extracting TikTok Sans Bold from ZIP…')
tiktok_bytes = None
with zipfile.ZipFile(io.BytesIO(tiktok_zip_bytes)) as zf:
    names = zf.namelist()
    print('Files in ZIP:', [n for n in names if n.lower().endswith('.ttf')])
    # Pick TikTokSans16pt-Bold.ttf — non-italic Bold at the standard 16pt optical size
    def _score(n):
        low = n.lower()
        if 'italic' in low: return 0          # never italic
        if '16pt-bold.ttf' in low: return 4  # exact match: TikTokSans16pt-Bold.ttf
        if '16pt' in low and low.endswith('bold.ttf'): return 3
        if low.endswith('-bold.ttf'): return 2
        if 'bold' in low: return 1
        return 0
    ttf_files = [n for n in names if n.lower().endswith('.ttf') and 'variable' not in n.lower()]
    ttf_files.sort(key=_score, reverse=True)
    if not ttf_files:
        raise RuntimeError('No TTF file found in TikTok Sans ZIP')
    chosen = ttf_files[0]
    print(f'Using: {chosen}')
    tiktok_bytes = zf.read(chosen)
print(f'TikTok Sans Bold: {len(tiktok_bytes):,} bytes')

# ── SSH connect ───────────────────────────────────────────────────────────────

print('\nConnecting…')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

def run(cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    result = (out.read() + err.read()).decode(errors='replace')
    result = result.encode('ascii', errors='replace').decode('ascii')
    print(f'>>> {cmd[:90]}\n{result.strip()}')
    return result.strip()

# ── Upload fonts ──────────────────────────────────────────────────────────────

sftp = ssh.open_sftp()

# Create fonts directory
run(f'mkdir -p {REMOTE_DIR}/fonts')

sftp.putfo(io.BytesIO(tiktok_bytes), f'{REMOTE_DIR}/fonts/TikTokSans-Bold.ttf')
print(f'Uploaded TikTokSans-Bold.ttf')

sftp.putfo(io.BytesIO(inter_bytes), f'{REMOTE_DIR}/fonts/Inter-Bold.ttf')
print(f'Uploaded Inter-Bold.ttf')

# ── Upload app files ──────────────────────────────────────────────────────────

for local, remote in FILES:
    with open(local, 'rb') as f:
        sftp.putfo(f, remote)
    print(f'Uploaded {remote}')

sftp.close()

# ── Restart + health check ────────────────────────────────────────────────────

print('\nRestarting hookshot…')
run('systemctl restart hookshot')
time.sleep(7)

health = run('curl -s -o /dev/null -w "%{http_code}" --max-time 15 http://127.0.0.1:5002/health 2>&1')
if '200' in health:
    print('\nSite is UP. All done!')
else:
    print(f'Health returned: {health} — retrying in 10s…')
    time.sleep(10)
    run('systemctl restart hookshot')
    time.sleep(8)
    health2 = run('curl -s -o /dev/null -w "%{http_code}" --max-time 15 http://127.0.0.1:5002/health 2>&1')
    print('Site UP.' if '200' in health2 else f'WARNING: still {health2}. Check manually.')

ssh.close()

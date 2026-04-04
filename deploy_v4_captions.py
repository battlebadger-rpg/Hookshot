"""
Deploy caption library v4:
- Upload changed app files
- Rename model Sylvia -> Silvia in the database
- Add new categories (already handled in app code, just data)
- Import 124 captions from caption_library_v4.csv
- Archive all old captions not in the new set
- Restart + health check
"""
import paramiko
import time
import io

HOST = '5.223.69.224'
USER = 'root'
PASS = 'EWL7ktAMeFrU'
REMOTE_DIR = '/root/hookshot/HookShot'
CSV_PATH = r'C:\Users\eden\Downloads\caption_library_v4.csv'

FILES = [
    (r'd:\AI tools\HookShot\HookShot\app.py',                  f'{REMOTE_DIR}/app.py'),
    (r'd:\AI tools\HookShot\HookShot\staff_permissions.json',  f'{REMOTE_DIR}/staff_permissions.json'),
    (r'd:\AI tools\HookShot\HookShot\templates\captions.html', f'{REMOTE_DIR}/templates/captions.html'),
]

print('Connecting…')
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

# Upload files
sftp = ssh.open_sftp()
for local, remote in FILES:
    with open(local, 'rb') as f:
        sftp.putfo(f, remote)
    print(f'Uploaded {remote}')

# Upload CSV
with open(CSV_PATH, 'rb') as f:
    csv_bytes = f.read()
remote_csv = '/tmp/caption_v4.csv'
sftp.putfo(io.BytesIO(csv_bytes), remote_csv)
print(f'Uploaded CSV ({len(csv_bytes)} bytes)')
sftp.close()

# Server-side migration + import script
script = r"""
import sys, csv, io
sys.path.insert(0, '/root/hookshot/HookShot')
import db

db.migrate_db()
print('Migration OK')

conn = db.get_connection()
cur = conn.cursor()

# 1. Rename Sylvia -> Silvia in models table
cur.execute("UPDATE models SET name='Silvia' WHERE name='Sylvia'")
print(f'Renamed Sylvia->Silvia in models: {cur.rowcount} rows')

# 2. Fix existing captions that reference Sylvia
cur.execute("SELECT id, models FROM captions WHERE models LIKE '%Sylvia%'")
rows = cur.fetchall()
for cid, mods in rows:
    fixed = ';'.join(
        ('Silvia' if m.strip() == 'Sylvia' else m.strip())
        for m in mods.split(';') if m.strip()
    )
    cur.execute("UPDATE captions SET models=? WHERE id=?", (fixed, cid))
print(f'Fixed Sylvia->Silvia in existing caption models: {len(rows)} rows')

# 3. Ensure all model names from CSV exist
ALL_MODELS = ['Annabelle','Silvia','Josie','Lulu','Klonoa','Naomi','Suki','Ahn']
for name in ALL_MODELS:
    cur.execute("INSERT OR IGNORE INTO models (name) VALUES (?)", (name,))
conn.commit()

cur.execute("SELECT id, name FROM models ORDER BY id")
print('Models:', [(r[0], r[1]) for r in cur.fetchall()])

# 4. Import captions from CSV
CAPTION_CATEGORIES = [
    'Social Commentary', 'Dark Humor', 'Innuendo', 'Relatable Humor', 'Thought Provoking',
    'Flat Commentary', 'Men / Relationships', 'Unhinged / Chaotic', 'Daddy / Good Girl', 'Side Chick',
]

with open('/tmp/caption_v4.csv', 'rb') as f:
    raw = f.read()
text = raw.decode('utf-8-sig')
reader = csv.DictReader(io.StringIO(text))
rows = list(reader)
print(f'CSV rows: {len(rows)}')

imported_ids = set()
added = updated = 0

for row in rows:
    cid = (row.get('ID') or '').strip()
    if not cid:
        continue
    category = (row.get('Category') or '').strip()
    caption_text = (row.get('Caption') or '').strip()
    if not caption_text:
        continue
    if category not in CAPTION_CATEGORIES:
        category = 'Social Commentary'
    try:
        times_used = int(row.get('Times Used') or 0)
    except:
        times_used = 0
    try:
        total_views = int(row.get('Total Views') or 0)
    except:
        total_views = 0

    # Normalise models: deduplicate, treat Sylvia==Silvia
    raw_models = row.get('Models') or ''
    seen = []
    seen_lower = set()
    for m in raw_models.split(';'):
        m = m.strip()
        if m == 'Sylvia':
            m = 'Silvia'
        if m and m.lower() not in seen_lower:
            seen.append(m)
            seen_lower.add(m.lower())
    models_val = ';'.join(seen)

    # Ensure each model exists
    for mname in seen:
        cur.execute("INSERT OR IGNORE INTO models (name) VALUES (?)", (mname,))

    cur.execute("SELECT id FROM captions WHERE id=?", (cid,))
    exists = cur.fetchone()
    if exists:
        cur.execute(
            "UPDATE captions SET category=?, caption=?, times_used=?, total_views=?, models=?, active=1 WHERE id=?",
            (category, caption_text, times_used, total_views, models_val, cid)
        )
        updated += 1
    else:
        cur.execute(
            "INSERT INTO captions (id, category, caption, times_used, total_views, models, active) VALUES (?,?,?,?,?,?,1)",
            (cid, category, caption_text, times_used, total_views, models_val)
        )
        added += 1
    imported_ids.add(cid)

# Archive captions not in the new CSV
cur.execute("SELECT id FROM captions")
all_ids = {r[0] for r in cur.fetchall()}
to_archive = all_ids - imported_ids
for aid in to_archive:
    cur.execute("UPDATE captions SET active=0 WHERE id=?", (aid,))

conn.commit()

active_count = cur.execute("SELECT COUNT(*) FROM captions WHERE active=1").fetchone()[0]
archived_count = cur.execute("SELECT COUNT(*) FROM captions WHERE active=0").fetchone()[0]
print(f'Done: added={added} updated={updated} archived={len(to_archive)}')
print(f'Active captions: {active_count}  |  Archived: {archived_count}')
conn.close()
"""

print('\nRunning server-side script…')
run(f"cat > /tmp/deploy_v4.py << 'PYEOF'\n{script}\nPYEOF")
run('python3 /tmp/deploy_v4.py 2>&1', timeout=60)

# Restart
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

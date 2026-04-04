"""
Deploy the full caption management system update:
- Upload changed app files
- Add Suki + Ahn models to the database
- Run DB migration (adds models/active columns to captions)
- Import captions from the local CSV file
- Restart service and verify health
"""
import paramiko
import time
import sys
import io

HOST = '5.223.69.224'
USER = 'root'
PASS = 'EWL7ktAMeFrU'
REMOTE_DIR = '/root/hookshot/HookShot'
CSV_PATH = r'C:\Users\eden\Downloads\caption_library_updated (1).csv'

FILES = [
    (r'd:\AI tools\HookShot\HookShot\app.py',               f'{REMOTE_DIR}/app.py'),
    (r'd:\AI tools\HookShot\HookShot\db.py',                f'{REMOTE_DIR}/db.py'),
    (r'd:\AI tools\HookShot\HookShot\staff_permissions.json', f'{REMOTE_DIR}/staff_permissions.json'),
    (r'd:\AI tools\HookShot\HookShot\templates\captions.html', f'{REMOTE_DIR}/templates/captions.html'),
]

print('Connecting to server…')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

def run(cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    result = out.read().decode(errors='replace') + err.read().decode(errors='replace')
    result = result.encode('ascii', errors='replace').decode('ascii')
    print(f'>>> {cmd[:80]}\n{result.strip()}')
    return result.strip()

# Upload files
sftp = ssh.open_sftp()
for local, remote in FILES:
    with open(local, 'rb') as f:
        sftp.putfo(f, remote)
    print(f'Uploaded {remote}')

# Upload CSV
print('Uploading caption CSV…')
with open(CSV_PATH, 'rb') as f:
    csv_data = f.read()
remote_csv = '/tmp/caption_import.csv'
sftp.putfo(io.BytesIO(csv_data), remote_csv)
print(f'Uploaded CSV ({len(csv_data)} bytes) to {remote_csv}')
sftp.close()

# Write and run the migration + import script on the server
migrate_script = r"""
import sys
sys.path.insert(0, '/root/hookshot/HookShot')
import db, csv, io

db.migrate_db()
print('Migration done.')

conn = db.get_connection()
cur = conn.cursor()

# Add Suki and Ahn models
for name in ('Suki', 'Ahn'):
    cur.execute('INSERT OR IGNORE INTO models (name) VALUES (?)', (name,))
conn.commit()
cur.execute('SELECT id, name FROM models ORDER BY id')
print('Models:', [(r[0], r[1]) for r in cur.fetchall()])

# Import captions from CSV
CAPTION_CATEGORIES = [
    'Social Commentary', 'Dark Humor', 'Innuendo', 'Relatable Humor', 'Thought Provoking'
]
with open('/tmp/caption_import.csv', 'rb') as f:
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
        category = CAPTION_CATEGORIES[0]
    try:
        times_used = int(row.get('Times Used') or 0)
    except:
        times_used = 0
    try:
        total_views = int(row.get('Total Views') or 0)
    except:
        total_views = 0
    models_val = ';'.join(
        m.strip() for m in (row.get('Models') or '').split(';') if m.strip()
    )
    active_raw = str(row.get('Active') or '1').strip().lower()
    active_val = 0 if active_raw in ('0','false','no','inactive','archived') else 1
    # Ensure model names exist
    for mname in models_val.split(';'):
        mname = mname.strip()
        if mname:
            cur.execute('INSERT OR IGNORE INTO models (name) VALUES (?)', (mname,))
    cur.execute('SELECT id FROM captions WHERE id = ?', (cid,))
    exists = cur.fetchone()
    if exists:
        cur.execute(
            'UPDATE captions SET category=?, caption=?, times_used=?, total_views=?, models=?, active=? WHERE id=?',
            (category, caption_text, times_used, total_views, models_val, active_val, cid)
        )
        updated += 1
    else:
        cur.execute(
            'INSERT INTO captions (id, category, caption, times_used, total_views, models, active) VALUES (?,?,?,?,?,?,?)',
            (cid, category, caption_text, times_used, total_views, models_val, active_val)
        )
        added += 1
    imported_ids.add(cid)

# Archive captions not in the CSV
cur.execute('SELECT id FROM captions')
all_ids = {r[0] for r in cur.fetchall()}
archive_ids = all_ids - imported_ids
for aid in archive_ids:
    cur.execute('UPDATE captions SET active = 0 WHERE id = ?', (aid,))
conn.commit()

total_active = cur.execute('SELECT COUNT(*) FROM captions WHERE active=1').fetchone()[0]
total_archived = cur.execute('SELECT COUNT(*) FROM captions WHERE active=0').fetchone()[0]
print(f'Done: added={added} updated={updated} archived={len(archive_ids)}')
print(f'Active captions: {total_active}  Archived: {total_archived}')
conn.close()
"""

print('\nRunning migration + import on server…')
# Write the script to a temp file on the server
run(f'cat > /tmp/run_migration.py << \'PYEOF\'\n{migrate_script}\nPYEOF')
result = run('python3 /tmp/run_migration.py 2>&1', timeout=60)

# Restart service
print('\nRestarting hookshot service…')
run('systemctl restart hookshot')
time.sleep(7)

# Health check
print('\nHealth check…')
health = run('curl -s -o /dev/null -w "%{http_code}" --max-time 15 http://127.0.0.1:5002/health 2>&1')
if '200' in health:
    print('\nSite is UP. All done!')
else:
    print(f'\nHealth check returned: {health}')
    print('Trying once more in 10s…')
    time.sleep(10)
    run('systemctl restart hookshot')
    time.sleep(8)
    health2 = run('curl -s -o /dev/null -w "%{http_code}" --max-time 15 http://127.0.0.1:5002/health 2>&1')
    if '200' in health2:
        print('Site is UP on retry.')
    else:
        print(f'WARNING: Health check still failed ({health2}). Check server manually.')

ssh.close()

import sys, os
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

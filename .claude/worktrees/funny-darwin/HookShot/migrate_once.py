import sys, os
os.chdir('/root/hookshot/HookShot')
sys.path.insert(0, '/root/hookshot/HookShot')
import db
db.init_db()
db.seed_and_migrate_if_empty('/root/hookshot/HookShot')
print('Migration done')

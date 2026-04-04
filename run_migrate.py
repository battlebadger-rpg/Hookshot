"""Run on server via SSH: cd /root/hookshot/HookShot && ./venv/bin/python -c 'exec(open(\"migrate_oneoff.py\").read())'"""
import os
import sys
os.chdir('/root/hookshot/HookShot')
sys.path.insert(0, '/root/hookshot/HookShot')
import db
db.init_db()
db.seed_and_migrate_if_empty('/root/hookshot/HookShot')
print('Migration done')

"""
One-time configuration: set Telegram group/topic destinations per Instagram account.

Fill in ACCOUNT_DESTINATIONS below with the chat_id and topic_id for each account.
- chat_id:  your Telegram group chat ID (negative number for supergroups, e.g. -1001234567890)
- topic_id: the thread ID of the specific topic within the group (find via Telegram API or bot)
             set to None if you want to send to the group's general chat (no topic)

Run this script once after collecting all your group/topic IDs.
Run it again any time you need to update destinations.
"""
import paramiko

HOST       = '5.223.69.224'
USER       = 'root'
PASS       = 'EWL7ktAMeFrU'
REMOTE_DIR = '/root/hookshot/HookShot'

# ── FILL THIS IN ──────────────────────────────────────────────────────────────
ACCOUNT_DESTINATIONS = {
    # 'instagram_account_name': {'chat_id': -1001234567890, 'topic_id': 123},
    # 'another_account':        {'chat_id': -1009876543210, 'topic_id': 456},
    # 'no_topic_account':       {'chat_id': -1001111111111, 'topic_id': None},
}
# ─────────────────────────────────────────────────────────────────────────────

if not ACCOUNT_DESTINATIONS:
    print('ACCOUNT_DESTINATIONS is empty — fill it in first.')
    exit(1)

print('Connecting…')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=20)

def run(cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    out.channel.recv_exit_status()
    result = (out.read() + err.read()).decode(errors='replace').strip()
    print(f'>>> {result}')
    return result

# Build SQL statements
sql_statements = []
for account_name, dest in ACCOUNT_DESTINATIONS.items():
    chat_id  = dest['chat_id']
    topic_id = dest.get('topic_id')
    topic_sql = str(topic_id) if topic_id is not None else 'NULL'
    sql_statements.append(
        f"UPDATE accounts SET tg_chat_id='{chat_id}', tg_topic_id={topic_sql}, auto_deliver=1 "
        f"WHERE name='{account_name}';"
    )

# Also disable auto_deliver for any accounts NOT in this list (optional — comment out if unwanted)
# sql_statements.append("UPDATE accounts SET auto_deliver=0 WHERE name NOT IN (" +
#     ",".join(f"'{n}'" for n in ACCOUNT_DESTINATIONS) + ");")

full_sql = '\n'.join(sql_statements)
script = f"""
import sys
sys.path.insert(0, '{REMOTE_DIR}')
import db
conn = db.get_connection()
cur = conn.cursor()
sql = '''{full_sql}'''
for stmt in sql.strip().split(';'):
    stmt = stmt.strip()
    if stmt:
        cur.execute(stmt)
        print(f'Rows affected: {{cur.rowcount}} — {{stmt[:80]}}')
conn.commit()

# Show final state
cur.execute("SELECT name, tg_chat_id, tg_topic_id, auto_deliver FROM accounts ORDER BY name")
print('\\nAccount destinations:')
for row in cur.fetchall():
    print(f"  {{row[0]}}: chat={{row[1]}} topic={{row[2]}} auto={{row[3]}}")
conn.close()
"""

# Write and run script on server
run(f"cat > /tmp/configure_auto_deliver.py << 'PYEOF'\n{script}\nPYEOF")
run(f'cd {REMOTE_DIR} && venv/bin/python /tmp/configure_auto_deliver.py 2>&1', timeout=30)

ssh.close()
print('\nDone. Run deploy_auto_deliver.py first if you haven\'t already.')

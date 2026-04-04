"""SQLite database for HookShot: accounts, captions, videos, batches, batch_items."""
import os
import sqlite3
import csv

def get_db_path():
    """Database file in app data root (same as uploads/outputs)."""
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, 'hookshot.db')

def get_connection():
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    return conn

def migrate_db():
    """Apply schema upgrades to existing databases (idempotent)."""
    conn = get_connection()
    cur = conn.cursor()
    # models table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # model_id column on accounts
    cur.execute("PRAGMA table_info(accounts)")
    cols = [r[1] for r in cur.fetchall()]
    if 'model_id' not in cols:
        cur.execute("ALTER TABLE accounts ADD COLUMN model_id INTEGER")
    # model_id + active column on videos
    cur.execute("PRAGMA table_info(videos)")
    vcols = [r[1] for r in cur.fetchall()]
    if 'model_id' not in vcols:
        cur.execute("ALTER TABLE videos ADD COLUMN model_id INTEGER")
    if 'active' not in vcols:
        cur.execute("ALTER TABLE videos ADD COLUMN active INTEGER DEFAULT 1")
        cur.execute("UPDATE videos SET active = 1 WHERE active IS NULL")
    # models + active columns on captions
    cur.execute("PRAGMA table_info(captions)")
    ccols = [r[1] for r in cur.fetchall()]
    if 'models' not in ccols:
        cur.execute("ALTER TABLE captions ADD COLUMN models TEXT DEFAULT ''")
    if 'active' not in ccols:
        cur.execute("ALTER TABLE captions ADD COLUMN active INTEGER DEFAULT 1")
        cur.execute("UPDATE captions SET active = 1 WHERE active IS NULL")
    # tg_chat_id, tg_topic_id, auto_deliver columns on accounts
    cur.execute("PRAGMA table_info(accounts)")
    acols = [r[1] for r in cur.fetchall()]
    for col, defn in [
        ('tg_chat_id',   'TEXT'),
        ('tg_topic_id',  'INTEGER'),
        ('auto_deliver', 'INTEGER DEFAULT 0'),
    ]:
        if col not in acols:
            cur.execute(f'ALTER TABLE accounts ADD COLUMN {col} {defn}')
    # output_seq — global counter for output filenames
    cur.execute("CREATE TABLE IF NOT EXISTS output_seq (next INTEGER)")
    cur.execute("SELECT COUNT(*) FROM output_seq")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO output_seq (next) VALUES (1)")
    conn.commit()
    conn.close()

def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            model_id INTEGER REFERENCES models(id),
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS captions (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            caption TEXT NOT NULL,
            times_used INTEGER DEFAULT 0,
            total_views INTEGER DEFAULT 0,
            models TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            duration TEXT NOT NULL,
            times_used INTEGER DEFAULT 0,
            model_id INTEGER REFERENCES models(id),
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS batches (
            id TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL,
            week_of TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );
        CREATE TABLE IF NOT EXISTS batch_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            video_id TEXT NOT NULL,
            caption_id TEXT NOT NULL,
            output_filename TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            posted_at TEXT,
            views_48h INTEGER,
            new_followers INTEGER,
            male_pct REAL,
            age_35_pct REAL,
            top_tier_pct REAL,
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (video_id) REFERENCES videos(id),
            FOREIGN KEY (caption_id) REFERENCES captions(id)
        );
    """)
    conn.commit()
    conn.close()

def seed_and_migrate_if_empty(data_root):
    """
    If no captions exist: seed accounts, then load captions/videos from CSV
    in data_root (or parent folder), and create legacy batch from performance_insights.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM captions")
    if cur.fetchone()[0] > 0:
        conn.close()
        return
    # Seed accounts
    for name in ('sugarbunnyana', 'anabelle.karel', 'anabelle.skits', 'germanblondiee'):
        cur.execute("INSERT OR IGNORE INTO accounts (name) VALUES (?)", (name,))
    conn.commit()
    parent = os.path.dirname(data_root)

    def csv_path(name):
        for base in (data_root, parent):
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
        return os.path.join(data_root, name)

    # Caption library
    path = csv_path('caption_library.csv')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            r = csv.DictReader(f)
            for row in r:
                cid = (row.get('ID') or '').strip()
                if not cid:
                    continue
                cur.execute(
                    "INSERT OR REPLACE INTO captions (id, category, caption, times_used, total_views) VALUES (?, ?, ?, ?, ?)",
                    (
                        cid,
                        (row.get('Category') or '').strip(),
                        (row.get('Caption') or '').strip(),
                        int(row.get('Times Used') or 0),
                        int(row.get('Total Views') or 0) if (row.get('Total Views') or '').strip() else 0,
                    ),
                )
    # Video library
    path = csv_path('video_library.csv')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            r = csv.DictReader(f)
            for row in r:
                vid = (row.get('Video ID') or '').strip()
                if not vid:
                    continue
                cur.execute(
                    "INSERT OR REPLACE INTO videos (id, description, duration, times_used) VALUES (?, ?, ?, ?)",
                    (
                        vid,
                        (row.get('Description') or '').strip(),
                        (row.get('Duration') or '').strip(),
                        int(row.get('Times Used') or 0),
                    ),
                )
    conn.commit()
    # Legacy batch from performance_insights (sugarbunnyana)
    path = csv_path('performance_insights.csv')
    if os.path.exists(path):
        cur.execute("SELECT id FROM accounts WHERE name = ?", ('sugarbunnyana',))
        row = cur.fetchone()
        if row:
            account_id = row[0]
            import uuid
            batch_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO batches (id, account_id, week_of) VALUES (?, ?, ?)",
                (batch_id, account_id, 'Legacy import'),
            )
            with open(path, 'r', encoding='utf-8') as f:
                r = csv.DictReader(f)
                for perf in r:
                    cap_id = (perf.get('Cap ID') or '').strip()
                    views_s = (perf.get('Views') or '').strip().replace(',', '')
                    video_used = (perf.get('Video Used') or '').strip()
                    # Parse "V02 — Beach wall..." -> V02
                    video_id = video_used.split('—')[0].strip() if '—' in video_used else video_used.split(',')[0].strip()
                    if not video_id.startswith('V'):
                        for prefix in ('V01', 'V02', 'V03', 'V04', 'V05', 'V06', 'V07', 'V08', 'V09', 'V10'):
                            if prefix in video_used or video_used.startswith(prefix):
                                video_id = prefix
                                break
                    views_48h = int(views_s) if views_s.isdigit() else None
                    new_fol = (perf.get('New Followers') or '').strip()
                    new_followers = int(new_fol) if new_fol.isdigit() else None
                    cur.execute(
                        """INSERT INTO batch_items (batch_id, video_id, caption_id, output_filename, posted_at, views_48h, new_followers)
                           VALUES (?, ?, ?, ?, datetime('now'), ?, ?)""",
                        (batch_id, video_id, cap_id, None, views_48h, new_followers),
                    )
            conn.commit()
    conn.close()

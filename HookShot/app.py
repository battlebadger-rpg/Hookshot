"""
HookShot — Video + caption batch tool with library, post tracking, and reporting.
"""
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
import subprocess
import os
import uuid
import shutil
import json
import sys
import platform
import functools
import random

# Path helpers (same as SnapText)
def _bundle_root():
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _resource(relative):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)

if hasattr(sys, '_MEIPASS'):
    FFMPEG = _resource('ffmpeg.exe')
    FFPROBE = _resource('ffprobe.exe')
elif platform.system() == 'Windows':
    FFMPEG = 'ffmpeg'
    FFPROBE = 'ffprobe'
else:
    FFMPEG = '/usr/bin/ffmpeg'
    FFPROBE = '/usr/bin/ffprobe'

if hasattr(sys, '_MEIPASS'):
    FONT_FILE = _resource('arialbd.ttf')
elif platform.system() == 'Windows':
    FONT_FILE = r'C:\Windows\Fonts\arialbd.ttf'
else:
    FONT_FILE = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'

app = Flask(__name__, template_folder=_resource('templates'))
app.secret_key = 'sntxt-s3cr3t-k3y-xK9mP2qR7vL4'

ROOT = _bundle_root()
UPLOAD_DIR = os.path.join(ROOT, 'uploads')
OUTPUT_DIR = os.path.join(ROOT, 'outputs')
LIBRARY_VIDEOS_DIR = os.path.join(ROOT, 'library_videos')
USERS_FILE = os.path.join(ROOT, 'users.json')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LIBRARY_VIDEOS_DIR, exist_ok=True)

# Database
import db
db.init_db()
db.seed_and_migrate_if_empty(ROOT)

def _load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def wrap_text(text, font_size, video_width):
    avg_char_width = font_size * 0.58
    usable_width = video_width * 0.88
    chars_per_line = max(1, int(usable_width / avg_char_width))
    words = text.split()
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        if len(test) <= chars_per_line:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [text]

def _render_video(src_path, caption_text, out_path, font_size, pos_y=0.5):
    """Overlay caption on video; write to out_path. Returns True on success."""
    probe = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src_path],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    vid = next(s for s in info['streams'] if s['codec_type'] == 'video')
    vw, vh = int(vid['width']), int(vid['height'])
    ext = os.path.splitext(out_path)[1] or '.mp4'
    pad_v = max(int(font_size * 0.45), 4)
    line_h = int(font_size * 1.3)
    lines = wrap_text(caption_text, font_size, vw)
    num_lines = len(lines)
    bar_h = num_lines * line_h + pad_v * 2
    bar_y = int(pos_y * vh - bar_h / 2)
    bar_y = max(0, min(vh - bar_h, bar_y))
    font_ffmpeg = FONT_FILE.replace('\\', '/').replace(':', '\\:')
    vf_parts = [f"drawbox=y={bar_y}:x=0:w=iw:h={bar_h}:color=black@0.72:t=fill"]
    for j, line in enumerate(lines):
        safe = line.replace("'", "\u2019").replace(":", "\\:").replace("\\", "\\\\")
        line_y = bar_y + pad_v + j * line_h
        vf_parts.append(
            f"drawtext=fontfile='{font_ffmpeg}':text='{safe}'"
            f":fontcolor=white:fontsize={font_size}"
            f":x=(w-tw)/2:y={line_y}"
            f":shadowcolor=black@0.3:shadowx=1:shadowy=1"
        )
    vf = ','.join(vf_parts)
    r = subprocess.run([
        FFMPEG, '-y', '-i', src_path,
        '-vf', vf,
        '-codec:a', 'copy',
        '-preset', 'ultrafast',
        out_path,
    ], capture_output=True)
    return r.returncode == 0

# ---------- Auth ----------
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('user'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        pin = request.form.get('pin', '').strip()
        users = _load_users()
        if username in users and str(users[username]) == pin:
            session['user'] = username
            return redirect(url_for('index'))
        error = 'Invalid username and PIN.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login_page'))

# ---------- Pages ----------
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/library')
@login_required
def library_page():
    return render_template('library.html')

@app.route('/batches')
@login_required
def batches_page():
    return render_template('batches.html')

@app.route('/batch/<batch_id>')
@login_required
def batch_detail_page(batch_id):
    return render_template('batch_detail.html', batch_id=batch_id)

@app.route('/report')
@login_required
def report_page():
    return render_template('report.html')

# ---------- API: Accounts ----------
@app.route('/api/accounts')
@login_required
def api_accounts():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM accounts ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return jsonify(accounts=[{'id': r[0], 'name': r[1]} for r in rows])

# ---------- API: Video library ----------
@app.route('/api/library/videos')
@login_required
def api_library_videos():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, description, duration, times_used FROM videos ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        vid, desc, dur, used = r[0], r[1], r[2], r[3]
        path = os.path.join(LIBRARY_VIDEOS_DIR, vid + '.mp4')
        has_file = os.path.isfile(path)
        out.append({'id': vid, 'description': desc, 'duration': dur, 'times_used': used, 'has_file': has_file})
    return jsonify(videos=out)

@app.route('/api/library/videos', methods=['POST'])
@login_required
def api_library_videos_add():
    description = (request.form.get('description') or '').strip()
    duration = (request.form.get('duration') or '').strip() or '0s'
    f = request.files.get('file')
    if not description or not f:
        return jsonify(error='description and file required'), 400
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM videos ORDER BY id")
    ids = [row[0] for row in cur.fetchall()]
    # Next id: V11, V12, ...
    next_num = 11
    for vid in ids:
        if vid.startswith('V') and len(vid) <= 4:
            try:
                n = int(vid[1:])
                if n >= next_num:
                    next_num = n + 1
            except ValueError:
                pass
    new_id = 'V' + str(next_num)
    ext = os.path.splitext(f.filename)[1] or '.mp4'
    path = os.path.join(LIBRARY_VIDEOS_DIR, new_id + ext)
    f.save(path)
    if ext != '.mp4':
        mp4_path = os.path.join(LIBRARY_VIDEOS_DIR, new_id + '.mp4')
        if path != mp4_path:
            subprocess.run([FFMPEG, '-y', '-i', path, '-c', 'copy', mp4_path], capture_output=True)
            try:
                os.remove(path)
            except OSError:
                pass
    cur.execute(
        "INSERT INTO videos (id, description, duration, times_used) VALUES (?, ?, ?, 0)",
        (new_id, description, duration),
    )
    conn.commit()
    conn.close()
    return jsonify(id=new_id, description=description, duration=duration, times_used=0, has_file=True)

@app.route('/api/library/videos/<video_id>/file', methods=['POST'])
@login_required
def api_library_videos_assign_file(video_id):
    f = request.files.get('file')
    if not f:
        return jsonify(error='file required'), 400
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify(error='video not found'), 404
    conn.close()
    ext = os.path.splitext(f.filename)[1] or '.mp4'
    path = os.path.join(LIBRARY_VIDEOS_DIR, video_id + '.mp4')
    f.save(path)
    return jsonify(ok=True)

# ---------- API: Batches ----------
@app.route('/api/batch/create', methods=['POST'])
@login_required
def api_batch_create():
    data = request.json or {}
    account_id = data.get('account_id')
    week_of = (data.get('week_of') or '').strip()
    if not account_id:
        return jsonify(error='account_id required'), 400
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM accounts WHERE id = ?", (account_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify(error='account not found'), 404
    cur.execute("SELECT id, caption FROM captions")
    captions = cur.fetchall()
    cur.execute("SELECT id FROM videos")
    video_ids = [row[0] for row in cur.fetchall()]
    # Only videos that have a file
    videos_with_files = [vid for vid in video_ids if os.path.isfile(os.path.join(LIBRARY_VIDEOS_DIR, vid + '.mp4'))]
    if len(captions) < 35 or len(videos_with_files) < 1:
        conn.close()
        return jsonify(error='Need at least 35 captions and 1 library video with file'), 400
    batch_id = str(uuid.uuid4())
    batch_dir = os.path.join(OUTPUT_DIR, batch_id)
    os.makedirs(batch_dir, exist_ok=True)
    cur.execute("INSERT INTO batches (id, account_id, week_of) VALUES (?, ?, ?)", (batch_id, account_id, week_of or None))
    font_pct = 3
    pos_y = 0.5
    files_created = []
    for i in range(35):
        cap_id, caption_text = random.choice(captions)
        video_id = random.choice(videos_with_files)
        src = os.path.join(LIBRARY_VIDEOS_DIR, video_id + '.mp4')
        if not os.path.isfile(src):
            continue
        probe = subprocess.run(
            [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src],
            capture_output=True, text=True,
        )
        info = json.loads(probe.stdout)
        vh = int(next(s for s in info['streams'] if s['codec_type'] == 'video')['height'])
        font_size = int((font_pct / 100) * vh)
        out_name = f"hook_{i+1}.mp4"
        out_path = os.path.join(batch_dir, out_name)
        if _render_video(src, caption_text, out_path, font_size, pos_y):
            files_created.append(out_name)
            cur.execute(
                """INSERT INTO batch_items (batch_id, video_id, caption_id, output_filename)
                   VALUES (?, ?, ?, ?)""",
                (batch_id, video_id, cap_id, out_name),
            )
            cur.execute("UPDATE captions SET times_used = times_used + 1 WHERE id = ?", (cap_id,))
            cur.execute("UPDATE videos SET times_used = times_used + 1 WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()
    return jsonify(batch_id=batch_id, files=files_created)

@app.route('/api/batches')
@login_required
def api_batches():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, b.week_of, b.created_at, a.name
        FROM batches b
        JOIN accounts a ON a.id = b.account_id
        ORDER BY b.created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return jsonify(batches=[{'id': r[0], 'week_of': r[1], 'created_at': r[2], 'account_name': r[3]} for r in rows])

@app.route('/api/batches/<batch_id>')
@login_required
def api_batch_detail(batch_id):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, account_id, week_of, created_at FROM batches WHERE id = ?", (batch_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify(error='not found'), 404
    cur.execute("SELECT a.name FROM accounts a JOIN batches b ON b.account_id = a.id WHERE b.id = ?", (batch_id,))
    acc = cur.fetchone()
    cur.execute("""
        SELECT bi.id, bi.video_id, bi.caption_id, bi.output_filename, bi.posted_at, bi.views_48h, c.caption
        FROM batch_items bi
        JOIN captions c ON c.id = bi.caption_id
        WHERE bi.batch_id = ?
        ORDER BY bi.id
    """, (batch_id,))
    items = cur.fetchall()
    conn.close()
    return jsonify(
        batch_id=row[0],
        account_id=row[1],
        week_of=row[2],
        created_at=row[3],
        account_name=acc[0] if acc else None,
        items=[{
            'id': i[0],
            'video_id': i[1],
            'caption_id': i[2],
            'output_filename': i[3],
            'posted_at': i[4],
            'views_48h': i[5],
            'caption_preview': (i[6][:60] + '...') if i[6] and len(i[6]) > 60 else (i[6] or ''),
        } for i in items],
    )

@app.route('/api/batches/<batch_id>/items/<int:item_id>/mark-posted', methods=['POST'])
@login_required
def api_mark_posted(batch_id, item_id):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE batch_items SET posted_at = datetime('now') WHERE batch_id = ? AND id = ?",
        (batch_id, item_id),
    )
    conn.commit()
    conn.close()
    return jsonify(ok=True)

@app.route('/api/batches/<batch_id>/items/<int:item_id>/views', methods=['POST'])
@login_required
def api_log_views(batch_id, item_id):
    data = request.json or {}
    views = data.get('views_48h')
    if views is not None:
        try:
            views = int(views)
        except (TypeError, ValueError):
            views = None
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE batch_items SET views_48h = ? WHERE batch_id = ? AND id = ?",
        (views, batch_id, item_id),
    )
    conn.commit()
    conn.close()
    return jsonify(ok=True)

# ---------- API: Reporting ----------
@app.route('/api/report/summary')
@login_required
def api_report_summary():
    conn = db.get_connection()
    cur = conn.cursor()
    # Top captions by sum of views_48h from batch_items
    cur.execute("""
        SELECT c.id, c.caption, c.category, c.times_used, COALESCE(SUM(bi.views_48h), 0) as total_views
        FROM captions c
        LEFT JOIN batch_items bi ON bi.caption_id = c.id AND bi.views_48h IS NOT NULL
        GROUP BY c.id
        ORDER BY total_views DESC
    """)
    captions = cur.fetchall()
    cur.execute("""
        SELECT video_id, caption_id, SUM(views_48h) as total
        FROM batch_items
        WHERE views_48h IS NOT NULL
        GROUP BY video_id, caption_id
        ORDER BY total DESC
    """)
    combos = cur.fetchall()
    cur.execute("""
        SELECT c.category, AVG(bi.views_48h) as avg_views, COUNT(*) as cnt
        FROM batch_items bi
        JOIN captions c ON c.id = bi.caption_id
        WHERE bi.views_48h IS NOT NULL
        GROUP BY c.category
    """)
    by_category = cur.fetchall()
    conn.close()
    return jsonify(
        top_captions=[{'id': r[0], 'caption': (r[1] or '')[:80], 'category': r[2], 'times_used': r[3], 'total_views': r[4]} for r in captions[:30]],
        top_combos=[{'video_id': r[0], 'caption_id': r[1], 'total_views': r[2]} for r in combos[:20]],
        by_category=[{'category': r[0], 'avg_views': r[1], 'count': r[2]} for r in by_category],
    )

# ---------- Download ----------
@app.route('/download/<batch_id>/<filename>')
@login_required
def download(batch_id, filename):
    d = os.path.join(OUTPUT_DIR, batch_id)
    return send_from_directory(d, filename, as_attachment=True)

@app.route('/download-all/<batch_id>')
@login_required
def download_all(batch_id):
    d = os.path.join(OUTPUT_DIR, batch_id)
    shutil.make_archive(d, 'zip', d)
    return send_from_directory(OUTPUT_DIR, batch_id + '.zip', as_attachment=True)

if __name__ == '__main__':
    import webbrowser
    import threading
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5002')).start()
    app.run(debug=False, port=5002)

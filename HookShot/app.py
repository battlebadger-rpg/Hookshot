"""

HookShot — Video + caption batch tool with library, post tracking, and reporting.

"""

from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for, Response

import subprocess

import os

import uuid

import shutil

import json

import threading

import sys

import platform

import functools

import random

import time

from datetime import datetime



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



if platform.system() == 'Windows':

    FONT_TIKTOK = r'C:\Windows\Fonts\arialbd.ttf'

    FONT_INTER  = r'C:\Windows\Fonts\arialbd.ttf'

else:

    FONT_TIKTOK = '/root/hookshot/HookShot/fonts/TikTokSans-Bold.ttf'

    FONT_INTER  = '/root/hookshot/HookShot/fonts/Inter-Bold.ttf'



app = Flask(__name__, template_folder=_resource('templates'))

app.secret_key = 'sntxt-s3cr3t-k3y-xK9mP2qR7vL4'



ROOT = _bundle_root()

UPLOAD_DIR = os.path.join(ROOT, 'uploads')

OUTPUT_DIR = os.path.join(ROOT, 'outputs')

LIBRARY_VIDEOS_DIR = os.path.join(ROOT, 'library_videos')

USERS_FILE = os.path.join(ROOT, 'users.json')

PERMISSIONS_FILE = os.path.join(ROOT, 'staff_permissions.json')

os.makedirs(UPLOAD_DIR, exist_ok=True)

os.makedirs(OUTPUT_DIR, exist_ok=True)

BATCH_GEN_DIR = os.path.join(ROOT, 'batch_output')
os.makedirs(LIBRARY_VIDEOS_DIR, exist_ok=True)
os.makedirs(BATCH_GEN_DIR, exist_ok=True)



def _cleanup_old_outputs(max_age_hours=24):

    """Delete output batch folders older than max_age_hours."""

    cutoff = time.time() - max_age_hours * 3600

    try:

        for name in os.listdir(OUTPUT_DIR):

            folder = os.path.join(OUTPUT_DIR, name)

            if os.path.isdir(folder) and os.path.getmtime(folder) < cutoff:

                shutil.rmtree(folder, ignore_errors=True)

    except Exception:

        pass



_cleanup_old_outputs()



AUTO_DELIVER_KEY = os.environ.get('HOOKSHOT_AUTO_KEY', '')



# ── Google Drive ──────────────────────────────────────────────────────────────

DRIVE_CREDS_PATH   = os.environ.get('GOOGLE_DRIVE_CREDENTIALS_PATH', '')

DRIVE_FOLDERS_FILE = os.path.join(ROOT, 'drive_folders.json')



_batch_jobs = {}   # job_id -> {status, done, total, model_name, dir, error, errors}






def _load_drive_folders():

    """Load model → Drive folder ID mapping from drive_folders.json."""

    if not os.path.exists(DRIVE_FOLDERS_FILE):

        return {}

    with open(DRIVE_FOLDERS_FILE, 'r', encoding='utf-8') as f:

        return json.load(f)



def _drive_upload(file_path, folder_id):

    """Upload file_path to the given Google Drive folder ID. Returns file ID on success."""

    from googleapiclient.discovery import build

    from googleapiclient.http import MediaFileUpload

    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(

        DRIVE_CREDS_PATH,

        scopes=['https://www.googleapis.com/auth/drive'],

    )

    service = build('drive', 'v3', credentials=creds)

    file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}

    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)

    result = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()

    return result.get('id')









def _run_batch_generate(job_id, model_id, model_name, count):
    """Background: render `count` unique video+caption combos and save to BATCH_GEN_DIR/job_id/."""
    FONT_PCT   = 3.5
    POS_Y      = 0.5
    TEXT_STYLE = 'clean'

    job     = _batch_jobs[job_id]
    job_dir = os.path.join(BATCH_GEN_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    job['dir'] = job_dir

    conn = db.get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM videos WHERE model_id=? AND COALESCE(active,1)=1",
            (model_id,)
        )
        video_rows = [r[0] for r in cur.fetchall()
                      if os.path.isfile(os.path.join(LIBRARY_VIDEOS_DIR, r[0] + '.mp4'))]

        cur.execute(
            """SELECT id, caption FROM captions
               WHERE COALESCE(active,1)=1
               AND (models='' OR models IS NULL
                    OR (',' || REPLACE(models,';',',') || ',') LIKE ('%,' || ? || ',%'))""",
            (model_name,)
        )
        captions = cur.fetchall()

        if not video_rows or not captions:
            job['status'] = 'error'
            job['error']  = f'No videos or captions found for model: {model_name}'
            return

        # Pre-probe videos for height
        video_heights = {}
        for vid_id in video_rows:
            try:
                src   = os.path.join(LIBRARY_VIDEOS_DIR, vid_id + '.mp4')
                probe = subprocess.run(
                    [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src],
                    capture_output=True, text=True, timeout=30,
                )
                info  = json.loads(probe.stdout)
                vh    = int(next(s for s in info['streams'] if s['codec_type'] == 'video')['height'])
                video_heights[vid_id] = vh
            except Exception:
                pass
        valid_videos = [v for v in video_rows if v in video_heights]
        if not valid_videos:
            job['status'] = 'error'
            job['error']  = 'Could not probe any source video files'
            return

        # All unique (video_id, cap_id, caption_text) combos — shuffle, take first `count`
        all_combos = [(v, c[0], c[1]) for v in valid_videos for c in captions]
        random.shuffle(all_combos)
        selected = all_combos[:count]

        job['total']  = len(selected)
        job['status'] = 'running'

        for i, (video_id, cap_id, caption_text) in enumerate(selected):
            src      = os.path.join(LIBRARY_VIDEOS_DIR, video_id + '.mp4')
            font_sz  = int(FONT_PCT / 100 * video_heights[video_id])
            out_name = f'{i + 1:03d}.mp4'
            out_path = os.path.join(job_dir, out_name)

            ok = _render_video(src, caption_text, out_path, font_sz, POS_Y, TEXT_STYLE)
            if ok:
                cur.execute("UPDATE captions SET times_used=times_used+1 WHERE id=?", (cap_id,))
                cur.execute("UPDATE videos  SET times_used=times_used+1 WHERE id=?", (video_id,))
                conn.commit()
                job['done'] += 1
            else:
                job['errors'] = job.get('errors', 0) + 1

        job['status'] = 'complete'

    except Exception as e:
        job['status'] = 'error'
        job['error']  = str(e)[:300]
    finally:
        conn.close()







@app.route('/api/render-overlay', methods=['POST'])

def api_render_overlay():

    """On-demand: receive an external video, render text overlay, upload to Drive."""

    key = request.headers.get('X-Auto-Key', '')

    if not AUTO_DELIVER_KEY or key != AUTO_DELIVER_KEY:

        return jsonify(error='forbidden'), 403

    video_file = request.files.get('video')

    model      = (request.form.get('model') or '').strip()

    overlay_id = (request.form.get('overlay_id') or '').strip()

    if not video_file or not model or not overlay_id:

        return jsonify(error='video, model, and overlay_id are required'), 400

    # Resolve Drive folder for this model

    drive_folders = _load_drive_folders()

    folder_id = next(

        (v for k, v in drive_folders.items() if k.lower() == model.lower()),

        None,

    )

    if not folder_id:

        return jsonify(error=f'No Drive folder configured for model: {model}'), 400

    # Strip "ov" prefix to get caption DB id (e.g. "ov034" -> "034")

    cap_id = overlay_id[2:] if overlay_id.lower().startswith('ov') else overlay_id

    conn = db.get_connection()

    cur  = conn.cursor()

    cur.execute("SELECT caption FROM captions WHERE id=?", (cap_id,))

    row = cur.fetchone()

    conn.close()

    if not row:

        return jsonify(error=f'overlay_id not found in caption library: {overlay_id}'), 400

    caption_text = row[0]

    # Save uploaded video to a temp path

    original_name = video_file.filename or 'video.mp4'

    base_name     = os.path.splitext(original_name)[0]

    tmp_id        = uuid.uuid4().hex

    tmp_in        = os.path.join(UPLOAD_DIR, f'overlay_in_{tmp_id}.mp4')

    out_name      = f'{model}_{overlay_id}_{base_name}.mp4'

    tmp_out       = os.path.join(UPLOAD_DIR, f'overlay_out_{tmp_id}.mp4')

    try:

        video_file.save(tmp_in)

        # Probe video for height to compute font size

        probe = subprocess.run(

            [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', tmp_in],

            capture_output=True, text=True, timeout=30,

        )

        try:

            info = json.loads(probe.stdout)

            vh   = int(next(s for s in info['streams'] if s['codec_type'] == 'video')['height'])

        except Exception:

            return jsonify(error='Could not probe uploaded video'), 500

        FONT_PCT = 3.5

        font_sz  = int((FONT_PCT / 100) * vh)

        render_ok = _render_video(tmp_in, caption_text, tmp_out, font_sz, pos_y=0.5, text_style='clean')

        if not render_ok:

            return jsonify(error='FFmpeg render failed'), 500

        # Rename output to final filename for Drive upload

        final_path = os.path.join(UPLOAD_DIR, out_name)

        os.replace(tmp_out, final_path)

        try:

            _drive_upload(final_path, folder_id)

        except Exception as drive_err:

            return jsonify(error=f'Drive upload failed: {drive_err}'), 500

        return jsonify(

            status='ok',

            overlay_id=overlay_id,

            drive_filename=out_name,

            drive_folder=f'{model.title()}/hookshot',

        )

    finally:

        for p in (tmp_in, tmp_out):

            try:

                if os.path.exists(p):

                    os.remove(p)

            except OSError:

                pass

        final_path_local = os.path.join(UPLOAD_DIR, out_name)

        try:

            if os.path.exists(final_path_local):

                os.remove(final_path_local)

        except OSError:

            pass









# Database (tables created lazily on first request to avoid blocking worker startup)

import db

_db_inited = False



def _load_users():

    if not os.path.exists(USERS_FILE):

        return {}

    with open(USERS_FILE, 'r', encoding='utf-8') as f:

        return json.load(f)



def _load_permissions():

    """Returns dict: username → list of allowed model names, or absent key = all access."""

    if not os.path.exists(PERMISSIONS_FILE):

        return {}

    with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:

        return json.load(f)



def _allowed_model_names(username):

    """Returns None for full access, or a (possibly empty) list of allowed model names."""

    perms = _load_permissions()

    if username not in perms:

        return None  # no restriction — full access (manager)

    return perms[username]  # list (may be empty)



def login_required(f):

    @functools.wraps(f)

    def decorated(*args, **kwargs):

        if not session.get('user'):

            return redirect(url_for('login_page'))

        return f(*args, **kwargs)

    return decorated






@app.route('/health')

def health():

    return 'ok', 200



@app.before_request

def _ensure_db():

    if request.path == '/health':

        return  # Skip DB init for health checks

    global _db_inited

    if not _db_inited:

        db.init_db()

        db.migrate_db()

        _db_inited = True



def wrap_text(text, font_size, video_width):

    avg_char_width = font_size * 0.65   # Inter Bold is wider than a generic font estimate

    usable_width = video_width * 0.82   # conservative safe zone to avoid edge bleed

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



def _render_video(src_path, caption_text, out_path, font_size, pos_y=0.5, text_style='classic'):

    """Overlay caption on video using the chosen text style; write to out_path. Returns True on success."""

    probe = subprocess.run(

        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src_path],

        capture_output=True, text=True,

    )

    info = json.loads(probe.stdout)

    vid = next(s for s in info['streams'] if s['codec_type'] == 'video')

    vw, vh = int(vid['width']), int(vid['height'])

    lines = wrap_text(caption_text, font_size, vw)

    vf_parts = []



    def _safe(line):

        return line.replace("'", "\u2019").replace(":", "\\:").replace("\\", "\\\\")



    def _ffmpeg_font(path):

        return path.replace('\\', '/').replace(':', '\\:')



    if text_style == 'clean':

        # Inter — white text with a thin black border, no background bar

        font_ffmpeg = _ffmpeg_font(FONT_INTER)

        line_h = int(font_size * 1.35)

        total_h = len(lines) * line_h

        start_y = max(0, int(pos_y * vh - total_h / 2))

        for j, line in enumerate(lines):

            line_y = start_y + j * line_h

            vf_parts.append(

                f"drawtext=fontfile='{font_ffmpeg}':text='{_safe(line)}'"

                f":fontcolor=white:fontsize={font_size}"

                f":x=(w-tw)/2:y={line_y}"

                f":borderw=2:bordercolor=black@0.9"

            )



    else:

        # classic — TikTok Sans, semi-transparent black bar behind white text

        font_ffmpeg = _ffmpeg_font(FONT_TIKTOK)

        pad_v = max(int(font_size * 0.45), 4)

        line_h = int(font_size * 1.3)

        num_lines = len(lines)

        bar_h = num_lines * line_h + pad_v * 2

        bar_y = int(pos_y * vh - bar_h / 2)

        bar_y = max(0, min(vh - bar_h, bar_y))

        vf_parts.append(f"drawbox=y={bar_y}:x=0:w=iw:h={bar_h}:color=black@0.72:t=fill")

        for j, line in enumerate(lines):

            line_y = bar_y + pad_v + j * line_h

            vf_parts.append(

                f"drawtext=fontfile='{font_ffmpeg}':text='{_safe(line)}'"

                f":fontcolor=white:fontsize={font_size}"

                f":x=(w-tw)/2:y={line_y}"

                f":shadowcolor=black@0.3:shadowx=1:shadowy=1"

            )



    vf = ','.join(vf_parts)

    r = subprocess.run([

        FFMPEG, '-y', '-noautorotate', '-i', src_path,

        '-vf', vf,

        '-c:v', 'libx264', '-preset', 'fast', '-crf', '28',

        '-c:a', 'copy',

        '-metadata:s:v:0', 'rotate=0',

        out_path,

    ], capture_output=True)

    return r.returncode == 0



def _create_preview_video(full_path):

    """Create a 480p low-res preview from the full-res output. Returns True on success."""

    base, ext = os.path.splitext(full_path)

    preview_path = base + '_preview' + ext

    r = subprocess.run([

        FFMPEG, '-y', '-i', full_path,

        '-vf', 'scale=-2:480',

        '-c:v', 'libx264', '-preset', 'fast', '-crf', '28',

        '-c:a', 'aac', '-b:a', '64k',

        preview_path,

    ], capture_output=True)

    return r.returncode == 0 and os.path.isfile(preview_path)



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



@app.route('/api/me')

@login_required

def api_me():

    username = session['user']

    allowed = _allowed_model_names(username)

    return jsonify(username=username, allowed_models=allowed)



# ---------- Pages ----------

@app.route('/')

@login_required

def index():

    return render_template('index.html')



@app.route('/library')

@login_required

def library_page():

    return render_template('library.html')



@app.route('/captions')

@login_required

def captions_page():

    return render_template('captions.html')



@app.route('/models')

@login_required

def models_page():

    return render_template('models.html')



# ── Models API ────────────────────────────────────────────────────────────────



@app.route('/api/models')

@login_required

def api_models_list():

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("SELECT id, name FROM models ORDER BY name")

    models = cur.fetchall()

    result = []

    for m in models:

        cur.execute("SELECT id, name FROM accounts WHERE model_id = ? ORDER BY name", (m[0],))

        accounts = cur.fetchall()

        result.append({

            'id': m[0],

            'name': m[1],

            'accounts': [{'id': a[0], 'name': a[1]} for a in accounts]

        })

    # Also fetch unassigned accounts

    cur.execute("SELECT id, name FROM accounts WHERE model_id IS NULL ORDER BY name")

    unassigned = cur.fetchall()

    conn.close()

    return jsonify(models=result, unassigned=[{'id': a[0], 'name': a[1]} for a in unassigned])



@app.route('/api/models', methods=['POST'])

@login_required

def api_models_add():

    data = request.json or {}

    name = (data.get('name') or '').strip()

    if not name:

        return jsonify(error='Model name is required'), 400

    conn = db.get_connection()

    cur = conn.cursor()

    try:

        cur.execute("INSERT INTO models (name) VALUES (?)", (name,))

        conn.commit()

        model_id = cur.lastrowid

    except Exception:

        conn.close()

        return jsonify(error='A model with that name already exists'), 400

    conn.close()

    return jsonify(id=model_id, name=name, accounts=[])



@app.route('/api/models/<int:model_id>', methods=['PUT'])

@login_required

def api_models_update(model_id):

    data = request.json or {}

    name = (data.get('name') or '').strip()

    if not name:

        return jsonify(error='Model name is required'), 400

    conn = db.get_connection()

    cur = conn.cursor()

    try:

        cur.execute("UPDATE models SET name = ? WHERE id = ?", (name, model_id))

        if cur.rowcount == 0:

            conn.close()

            return jsonify(error='Model not found'), 404

        conn.commit()

    except Exception:

        conn.close()

        return jsonify(error='A model with that name already exists'), 400

    conn.close()

    return jsonify(ok=True)



@app.route('/api/models/<int:model_id>', methods=['DELETE'])

@login_required

def api_models_delete(model_id):

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM accounts WHERE model_id = ?", (model_id,))

    if cur.fetchone()[0] > 0:

        conn.close()

        return jsonify(error='Cannot delete — model still has accounts assigned'), 400

    cur.execute("DELETE FROM models WHERE id = ?", (model_id,))

    conn.commit()

    conn.close()

    return jsonify(ok=True)



@app.route('/api/models/<int:model_id>/accounts', methods=['POST'])

@login_required

def api_models_add_account(model_id):

    data = request.json or {}

    name = (data.get('name') or '').strip()

    if not name:

        return jsonify(error='Account name is required'), 400

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("SELECT id FROM models WHERE id = ?", (model_id,))

    if not cur.fetchone():

        conn.close()

        return jsonify(error='Model not found'), 404

    try:

        cur.execute("INSERT INTO accounts (name, model_id) VALUES (?, ?)", (name, model_id))

        conn.commit()

        acc_id = cur.lastrowid

    except Exception:

        conn.close()

        return jsonify(error='An account with that name already exists'), 400

    conn.close()

    return jsonify(id=acc_id, name=name)



@app.route('/api/accounts/<int:acc_id>', methods=['PUT'])

@login_required

def api_accounts_update(acc_id):

    data = request.json or {}

    name = (data.get('name') or '').strip()

    model_id = data.get('model_id')  # int or None

    conn = db.get_connection()

    cur = conn.cursor()

    updates, params = [], []

    if name:

        updates.append("name = ?"); params.append(name)

    if 'model_id' in data:

        updates.append("model_id = ?"); params.append(model_id)

    if not updates:

        conn.close()

        return jsonify(error='Nothing to update'), 400

    params.append(acc_id)

    cur.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", params)

    if cur.rowcount == 0:

        conn.close()

        return jsonify(error='Account not found'), 404

    conn.commit()

    conn.close()

    return jsonify(ok=True)



@app.route('/api/accounts/<int:acc_id>', methods=['DELETE'])

@login_required

def api_accounts_delete(acc_id):

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM batches WHERE account_id = ?", (acc_id,))

    if cur.fetchone()[0] > 0:

        conn.close()

        return jsonify(error='Cannot delete — account has existing batches'), 400

    cur.execute("DELETE FROM accounts WHERE id = ?", (acc_id,))

    conn.commit()

    conn.close()

    return jsonify(ok=True)



# ── Caption API ───────────────────────────────────────────────────────────────



CAPTION_CATEGORIES = [

    'Social Commentary', 'Dark Humor', 'Innuendo', 'Relatable Humor', 'Thought Provoking',

    'Flat Commentary', 'Men / Relationships', 'Unhinged / Chaotic', 'Daddy / Good Girl', 'Side Chick',

]



@app.route('/api/captions')

@login_required

def api_captions_list():

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("SELECT id, category, caption, times_used, total_views, COALESCE(models,''), COALESCE(active,1) FROM captions ORDER BY id")

    rows = cur.fetchall()

    conn.close()

    return jsonify(captions=[

        {'id': r[0], 'category': r[1], 'caption': r[2], 'times_used': r[3], 'total_views': r[4],

         'models': r[5], 'active': bool(r[6])}

        for r in rows

    ])



@app.route('/api/captions', methods=['POST'])

@login_required

def api_captions_add():

    data = request.json or {}

    caption_text = (data.get('caption') or '').strip()

    category = (data.get('category') or '').strip()

    if not caption_text:

        return jsonify(error='Caption text is required'), 400

    if category not in CAPTION_CATEGORIES:

        return jsonify(error='Invalid category'), 400

    conn = db.get_connection()

    cur = conn.cursor()

    # Generate next sequential ID (zero-padded to 3 digits)

    cur.execute("SELECT id FROM captions ORDER BY CAST(id AS INTEGER) DESC LIMIT 1")

    last = cur.fetchone()

    next_id = str(int(last[0]) + 1).zfill(3) if last else '001'

    cur.execute(

        "INSERT INTO captions (id, category, caption, times_used, total_views, models, active) VALUES (?, ?, ?, 0, 0, '', 1)",

        (next_id, category, caption_text)

    )

    conn.commit()

    conn.close()

    return jsonify(id=next_id, category=category, caption=caption_text, times_used=0, total_views=0, models='', active=True)



@app.route('/api/captions/<cap_id>', methods=['PUT'])

@login_required

def api_captions_update(cap_id):

    data = request.json or {}

    caption_text = (data.get('caption') or '').strip()

    category = (data.get('category') or '').strip()

    if not caption_text:

        return jsonify(error='Caption text is required'), 400

    if category not in CAPTION_CATEGORIES:

        return jsonify(error='Invalid category'), 400

    models_val = (data.get('models') or '').strip()

    active_val = 1 if data.get('active', True) else 0

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute(

        "UPDATE captions SET caption = ?, category = ?, models = ?, active = ? WHERE id = ?",

        (caption_text, category, models_val, active_val, cap_id)

    )

    if cur.rowcount == 0:

        conn.close()

        return jsonify(error='Caption not found'), 404

    conn.commit()

    conn.close()

    return jsonify(ok=True)



@app.route('/api/captions/export')

@login_required

def api_captions_export():

    """Export all captions as CSV for editing."""

    import csv

    import io

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute(

        "SELECT id, category, caption, times_used, total_views, COALESCE(models,''), COALESCE(active,1) FROM captions ORDER BY id"

    )

    rows = cur.fetchall()

    conn.close()

    buf = io.StringIO()

    w = csv.writer(buf)

    w.writerow(['ID', 'Category', 'Caption', 'Times Used', 'Total Views', 'Models', 'Active'])

    for r in rows:

        w.writerow([r[0], r[1], r[2], r[3] or 0, r[4] or 0, r[5], r[6]])

    csv_bytes = buf.getvalue().encode('utf-8-sig')  # BOM for Excel

    return Response(

        csv_bytes,

        mimetype='text/csv; charset=utf-8',

        headers={'Content-Disposition': 'attachment; filename=caption_library_export.csv'}

    )



@app.route('/api/captions/import', methods=['POST'])

@login_required

def api_captions_import():

    """

    Import captions from a CSV upload.

    - Updates existing captions (matched by ID).

    - Inserts new captions.

    - Archives (active=0) any captions NOT present in the CSV.

    - Ensures models listed in the CSV exist in the models table.

    """

    import csv

    import io

    if 'file' not in request.files:

        return jsonify(error='No file uploaded'), 400

    f = request.files['file']

    if not f.filename.lower().endswith('.csv'):

        return jsonify(error='File must be a CSV'), 400

    raw = f.read()

    # Strip UTF-8 BOM if present

    text = raw.decode('utf-8-sig')

    reader = csv.DictReader(io.StringIO(text))

    rows = list(reader)

    if not rows:

        return jsonify(error='CSV is empty'), 400

    conn = db.get_connection()

    cur = conn.cursor()

    # Ensure all model names from CSV exist in the models table

    all_model_names = set()

    for row in rows:

        for m in (row.get('Models') or '').split(';'):

            m = m.strip()

            if m:

                all_model_names.add(m)

    for mname in all_model_names:

        cur.execute("INSERT OR IGNORE INTO models (name) VALUES (?)", (mname,))

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

        except ValueError:

            times_used = 0

        try:

            total_views = int(row.get('Total Views') or 0)

        except ValueError:

            total_views = 0

        models_val = ';'.join(

            m.strip() for m in (row.get('Models') or '').split(';') if m.strip()

        )

        # Active column in CSV: 1/0 or yes/no or blank (default active)

        active_raw = str(row.get('Active') or '1').strip().lower()

        active_val = 0 if active_raw in ('0', 'false', 'no', 'inactive', 'archived') else 1

        cur.execute("SELECT id FROM captions WHERE id = ?", (cid,))

        exists = cur.fetchone()

        if exists:

            cur.execute(

                """UPDATE captions

                   SET category=?, caption=?, times_used=?, total_views=?, models=?, active=?

                   WHERE id=?""",

                (category, caption_text, times_used, total_views, models_val, active_val, cid)

            )

            updated += 1

        else:

            cur.execute(

                """INSERT INTO captions (id, category, caption, times_used, total_views, models, active)

                   VALUES (?, ?, ?, ?, ?, ?, ?)""",

                (cid, category, caption_text, times_used, total_views, models_val, active_val)

            )

            added += 1

        imported_ids.add(cid)

    # Archive captions not present in the CSV

    cur.execute("SELECT id FROM captions")

    all_ids = {r[0] for r in cur.fetchall()}

    archive_ids = all_ids - imported_ids

    archived = 0

    for aid in archive_ids:

        cur.execute("UPDATE captions SET active = 0 WHERE id = ?", (aid,))

        archived += 1

    conn.commit()

    conn.close()

    return jsonify(ok=True, added=added, updated=updated, archived=archived)



@app.route('/api/captions/<cap_id>', methods=['DELETE'])

@login_required

def api_captions_delete(cap_id):

    conn = db.get_connection()

    cur = conn.cursor()

    # Prevent deletion if used in any batch items

    cur.execute("SELECT COUNT(*) FROM batch_items WHERE caption_id = ?", (cap_id,))

    count = cur.fetchone()[0]

    if count > 0:

        conn.close()

        return jsonify(error=f'Cannot delete — used in {count} batch item(s)'), 400

    cur.execute("DELETE FROM captions WHERE id = ?", (cap_id,))

    conn.commit()

    conn.close()

    return jsonify(ok=True)



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

    username = session['user']

    allowed = _allowed_model_names(username)

    conn = db.get_connection()

    cur = conn.cursor()

    if allowed is None:

        # Full access — no filter

        cur.execute("""

            SELECT a.id, a.name, a.model_id, m.name as model_name

            FROM accounts a

            LEFT JOIN models m ON m.id = a.model_id

            ORDER BY m.name, a.name

        """)

    elif len(allowed) == 0:

        # No access at all

        conn.close()

        return jsonify(accounts=[])

    else:

        placeholders = ','.join('?' * len(allowed))

        cur.execute(f"""

            SELECT a.id, a.name, a.model_id, m.name as model_name

            FROM accounts a

            JOIN models m ON m.id = a.model_id

            WHERE m.name IN ({placeholders})

            ORDER BY m.name, a.name

        """, allowed)

    rows = cur.fetchall()

    conn.close()

    return jsonify(accounts=[{'id': r[0], 'name': r[1], 'model_id': r[2], 'model_name': r[3]} for r in rows])



# ---------- API: Video library ----------

@app.route('/api/library/videos')

@login_required

def api_library_videos():

    model_id_filter = request.args.get('model_id')

    conn = db.get_connection()

    cur = conn.cursor()

    if model_id_filter:

        cur.execute("""

            SELECT v.id, v.description, v.duration, v.times_used, v.model_id, m.name,

                   COALESCE(v.active, 1)

            FROM videos v LEFT JOIN models m ON m.id = v.model_id

            WHERE v.model_id = ?

            ORDER BY v.id

        """, (model_id_filter,))

    else:

        cur.execute("""

            SELECT v.id, v.description, v.duration, v.times_used, v.model_id, m.name,

                   COALESCE(v.active, 1)

            FROM videos v LEFT JOIN models m ON m.id = v.model_id

            ORDER BY v.id

        """)

    rows = cur.fetchall()

    conn.close()

    out = []

    for r in rows:

        vid, desc, dur, used, mid, mname, active = r[0], r[1], r[2], r[3], r[4], r[5], r[6]

        path = os.path.join(LIBRARY_VIDEOS_DIR, vid + '.mp4')

        has_file = os.path.isfile(path)

        out.append({'id': vid, 'description': desc, 'duration': dur, 'times_used': used,

                    'has_file': has_file, 'model_id': mid, 'model_name': mname,

                    'active': bool(active)})

    return jsonify(videos=out)



def _save_library_video(f, dest_id):

    """Save uploaded video file to library_videos/<dest_id>.mp4, converting if needed.

    Returns (True, None) on success or (False, error_message) on failure."""

    ext = os.path.splitext(f.filename)[1].lower() or '.mp4'

    tmp_path = os.path.join(LIBRARY_VIDEOS_DIR, dest_id + '_tmp' + ext)

    mp4_path = os.path.join(LIBRARY_VIDEOS_DIR, dest_id + '.mp4')

    f.save(tmp_path)

    if ext == '.mp4':

        try:

            os.replace(tmp_path, mp4_path)

        except OSError as e:

            return False, str(e)

    else:

        result = subprocess.run(

            [FFMPEG, '-y', '-i', tmp_path,

             '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',

             '-c:a', 'aac', '-b:a', '128k',

             mp4_path],

            capture_output=True

        )

        try:

            os.remove(tmp_path)

        except OSError:

            pass

        if result.returncode != 0:

            err = result.stderr.decode(errors='replace')[-400:]

            return False, f'FFmpeg conversion failed: {err}'

    return True, None





@app.route('/api/library/videos', methods=['POST'])

@login_required

def api_library_videos_add():

    description = (request.form.get('description') or '').strip()

    duration = (request.form.get('duration') or '').strip() or '0s'

    model_id_raw = (request.form.get('model_id') or '').strip()

    model_id = int(model_id_raw) if model_id_raw.isdigit() else None

    f = request.files.get('file')

    if not description or not f:

        return jsonify(error='description and file required'), 400

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("SELECT id FROM videos ORDER BY id")

    ids = [row[0] for row in cur.fetchall()]

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

    ok, err = _save_library_video(f, new_id)

    if not ok:

        conn.close()

        return jsonify(error=err), 500

    cur.execute(

        "INSERT INTO videos (id, description, duration, times_used, model_id) VALUES (?, ?, ?, 0, ?)",

        (new_id, description, duration, model_id),

    )

    conn.commit()

    conn.close()

    return jsonify(id=new_id, description=description, duration=duration, times_used=0,

                   has_file=True, model_id=model_id)



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

    ok, err = _save_library_video(f, video_id)

    if not ok:

        return jsonify(error=err), 500

    return jsonify(ok=True)



@app.route('/api/library/videos/<video_id>/active', methods=['POST'])

@login_required

def api_library_videos_toggle_active(video_id):

    data = request.json or {}

    active = 1 if data.get('active') else 0

    conn = db.get_connection()

    cur = conn.cursor()

    cur.execute("UPDATE videos SET active = ? WHERE id = ?", (active, video_id))

    if cur.rowcount == 0:

        conn.close()

        return jsonify(error='video not found'), 404

    conn.commit()

    conn.close()

    return jsonify(ok=True, active=active)



# ---------- API: Batches ----------

@app.route('/api/batch/create', methods=['POST'])

@login_required

def api_batch_create():

    data = request.json or {}

    account_id = data.get('account_id')

    batch_size = int(data.get('batch_size') or 5)

    batch_size = max(1, min(10, batch_size))

    if not account_id:

        return jsonify(error='account_id required'), 400

    username = session['user']

    allowed = _allowed_model_names(username)

    conn = db.get_connection()

    cur = conn.cursor()

    # Fetch account with its model

    cur.execute("""

        SELECT a.id, a.name, a.model_id, m.name as model_name

        FROM accounts a LEFT JOIN models m ON m.id = a.model_id

        WHERE a.id = ?

    """, (account_id,))

    acc_row = cur.fetchone()

    if not acc_row:

        conn.close()

        return jsonify(error='account not found'), 404

    acc_name_val = acc_row[1]

    acc_model_id = acc_row[2]

    acc_model_name = acc_row[3]

    # Enforce staff permissions

    if allowed is not None:

        if not acc_model_name or acc_model_name not in allowed:

            conn.close()

            return jsonify(error='You do not have permission to create batches for this model'), 403

    # Auto-generate batch name

    date_str = datetime.now().strftime('%a %d %b %Y')

    auto_name = f"{acc_model_name} \u2014 {acc_name_val} \u2014 {date_str}" if acc_model_name else f"{acc_name_val} \u2014 {date_str}"

    # Only use active captions assigned to this model (or unassigned captions as fallback)

    if acc_model_name:

        cur.execute(

            """SELECT id, caption FROM captions

               WHERE COALESCE(active,1)=1

               AND (models='' OR models IS NULL

                    OR (',' || REPLACE(models,';',',') || ',') LIKE ('%,' || ? || ',%'))""",

            (acc_model_name,)

        )

    else:

        cur.execute("SELECT id, caption FROM captions WHERE COALESCE(active,1)=1")

    captions = cur.fetchall()

    # Filter videos by model — if account has a model, only use active videos for that model

    if acc_model_id:

        cur.execute("SELECT id FROM videos WHERE model_id = ? AND COALESCE(active, 1) = 1", (acc_model_id,))

    else:

        cur.execute("SELECT id FROM videos WHERE COALESCE(active, 1) = 1")

    video_ids = [row[0] for row in cur.fetchall()]

    # Only videos that have a file

    videos_with_files = [vid for vid in video_ids if os.path.isfile(os.path.join(LIBRARY_VIDEOS_DIR, vid + '.mp4'))]

    if len(captions) < 1 or len(videos_with_files) < 1:

        conn.close()

        model_hint = f" for {acc_model_name}" if acc_model_name else ""

        return jsonify(error=f'Need at least 1 caption and 1 library video with file{model_hint}'), 400

    batch_id = str(uuid.uuid4())

    batch_dir = os.path.join(OUTPUT_DIR, batch_id)

    os.makedirs(batch_dir, exist_ok=True)

    cur.execute("INSERT INTO batches (id, account_id, week_of) VALUES (?, ?, ?)", (batch_id, account_id, auto_name))

    # Reserve next N sequence numbers for output filenames (00001.mp4, 00002.mp4, ...)

    cur.execute("SELECT next FROM output_seq")

    seq_start = cur.fetchone()[0]

    cur.execute("UPDATE output_seq SET next = next + ?", (batch_size,))

    text_style = data.get('text_style', 'classic')

    if text_style not in ('classic', 'clean'):

        text_style = 'classic'

    font_pct_map = {'classic': 3.0, 'clean': 3.5}

    font_pct = font_pct_map[text_style]

    pos_y = 0.5

    files_created = []

    for i in range(batch_size):

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

        out_name = f"{seq_start + i:05d}.mp4"

        out_path = os.path.join(batch_dir, out_name)

        if _render_video(src, caption_text, out_path, font_size, pos_y, text_style):

            _create_preview_video(out_path)  # 480p preview for fast batch review

            files_created.append(out_name)

            cur.execute(

                """INSERT INTO batch_items (batch_id, video_id, caption_id, output_filename, posted_at)

                   VALUES (?, ?, ?, ?, datetime('now'))""",

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



# ---------- Download / Preview ----------

@app.route('/preview/<batch_id>/<filename>')

@login_required

def preview_video(batch_id, filename):

    """Serve low-res preview when available, else full-res. Inline for browser playback."""

    d = os.path.join(OUTPUT_DIR, batch_id)

    base, ext = os.path.splitext(filename)

    preview_name = base + '_preview' + ext

    preview_path = os.path.join(d, preview_name)

    if os.path.isfile(preview_path):

        return send_from_directory(d, preview_name, as_attachment=False, mimetype='video/mp4')

    return send_from_directory(d, filename, as_attachment=False, mimetype='video/mp4')



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



@app.route('/download-approved/<batch_id>', methods=['POST'])

@login_required

def download_approved(batch_id):

    import io, zipfile

    from flask import send_file

    data = request.json or {}

    approved_files = data.get('files', [])

    batch_dir = os.path.join(OUTPUT_DIR, batch_id)

    buf = io.BytesIO()

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:

        for fname in approved_files:

            safe = os.path.basename(fname)

            fpath = os.path.join(batch_dir, safe)

            if os.path.isfile(fpath):

                zf.write(fpath, safe)

    buf.seek(0)

    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='approved_videos.zip')




# ── Manual Batch Generation ───────────────────────────────────────────────────

@app.route('/api/batch-generate', methods=['POST'])
@login_required
def api_batch_generate():
    data       = request.json or {}
    model_name = (data.get('model_name') or '').strip()
    count      = max(1, min(int(data.get('count', 140)), 500))
    if not model_name:
        return jsonify(error='model_name is required'), 400
    conn = db.get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM models WHERE LOWER(name) = LOWER(?)", (model_name,))
    m = cur.fetchone()
    conn.close()
    if not m:
        return jsonify(error=f'Model not found: {model_name}'), 404
    job_id = str(uuid.uuid4())
    _batch_jobs[job_id] = {
        'status': 'starting', 'done': 0, 'total': count,
        'model_name': model_name, 'model_id': m[0],
        'created_at': time.time(), 'dir': None, 'error': None, 'errors': 0,
    }
    threading.Thread(
        target=_run_batch_generate, args=(job_id, m[0], model_name, count), daemon=True
    ).start()
    return jsonify(job_id=job_id, status='starting', total=count)


@app.route('/api/batch-status/<job_id>')
@login_required
def api_batch_status_route(job_id):
    job = _batch_jobs.get(job_id)
    if not job:
        return jsonify(error='Job not found'), 404
    return jsonify(
        status=job['status'], done=job['done'], total=job['total'],
        model_name=job['model_name'], error=job.get('error'), errors=job.get('errors', 0),
    )


@app.route('/api/batch-download/<job_id>')
@login_required
def api_batch_download_route(job_id):
    from flask import send_file as _sf
    job = _batch_jobs.get(job_id)
    if not job:
        return jsonify(error='Job not found'), 404
    if job['status'] != 'complete':
        return jsonify(error='Batch not ready — status: ' + job['status']), 400
    job_dir = job.get('dir', '')
    if not os.path.isdir(job_dir):
        return jsonify(error='Batch files not found on disk'), 404
    zip_path = job_dir + '.zip'
    if not os.path.isfile(zip_path):
        shutil.make_archive(job_dir, 'zip', job_dir)
    slug    = job['model_name'].lower().replace(' ', '_')
    dl_name = f'hookshot_{slug}_{datetime.now().strftime("%Y%m%d")}.zip'
    return _sf(zip_path, mimetype='application/zip', as_attachment=True, download_name=dl_name)

@app.route('/api/deliver', methods=['POST'])
@login_required
def api_deliver():
    """Manual Drive delivery: render and upload videos for each model in drive_folders.json."""
    if not DRIVE_CREDS_PATH:
        return jsonify(error='Google Drive credentials not configured'), 400

    data = request.json or {}
    requested_models = data.get('models')  # None = all models
    count = int(data.get('count', 1))
    count = max(1, count)

    drive_folders = _load_drive_folders()
    if not drive_folders:
        return jsonify(error='No Drive folders configured in drive_folders.json'), 400

    model_names = requested_models if requested_models else list(drive_folders.keys())

    FONT_PCT   = 3.5
    POS_Y      = 0.5
    TEXT_STYLE = 'clean'

    results = []
    total_uploaded = 0
    total_errors   = 0

    conn = db.get_connection()
    cur  = conn.cursor()
    try:
        for model_name in model_names:
            folder_id = next(
                (v for k, v in drive_folders.items() if k.lower() == model_name.lower()),
                None,
            )
            if not folder_id:
                results.append({'model': model_name, 'uploaded': 0, 'errors': 0,
                                 'skipped': True, 'reason': 'No Drive folder configured'})
                continue

            cur.execute("SELECT id FROM models WHERE LOWER(name)=LOWER(?)", (model_name,))
            row = cur.fetchone()
            if not row:
                results.append({'model': model_name, 'uploaded': 0, 'errors': 1,
                                 'reason': 'Model not found in database'})
                total_errors += 1
                continue
            model_id = row[0]

            cur.execute(
                "SELECT id FROM videos WHERE model_id=? AND COALESCE(active,1)=1",
                (model_id,)
            )
            video_rows = [r[0] for r in cur.fetchall()
                          if os.path.isfile(os.path.join(LIBRARY_VIDEOS_DIR, r[0] + '.mp4'))]

            cur.execute(
                """SELECT id, caption FROM captions
                   WHERE COALESCE(active,1)=1
                   AND (models='' OR models IS NULL
                        OR (',' || REPLACE(models,';',',') || ',') LIKE ('%,' || ? || ',%'))""",
                (model_name,)
            )
            captions = cur.fetchall()

            if not video_rows or not captions:
                reason = 'No videos found' if not video_rows else 'No captions found'
                results.append({'model': model_name, 'uploaded': 0, 'errors': 1, 'reason': reason})
                total_errors += 1
                continue

            # Probe heights
            video_heights = {}
            for vid_id in video_rows:
                try:
                    src   = os.path.join(LIBRARY_VIDEOS_DIR, vid_id + '.mp4')
                    probe = subprocess.run(
                        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src],
                        capture_output=True, text=True, timeout=30,
                    )
                    info  = json.loads(probe.stdout)
                    vh    = int(next(s for s in info['streams'] if s['codec_type'] == 'video')['height'])
                    video_heights[vid_id] = vh
                except Exception:
                    pass
            valid_videos = [v for v in video_rows if v in video_heights]
            if not valid_videos:
                results.append({'model': model_name, 'uploaded': 0, 'errors': 1,
                                 'reason': 'Could not probe any video files'})
                total_errors += 1
                continue

            all_combos = [(v, c[0], c[1]) for v in valid_videos for c in captions]
            random.shuffle(all_combos)
            selected = all_combos[:count]

            uploaded = 0
            errors   = 0
            for video_id, cap_id, caption_text in selected:
                src      = os.path.join(LIBRARY_VIDEOS_DIR, video_id + '.mp4')
                font_sz  = int(FONT_PCT / 100 * video_heights[video_id])
                tmp_name = f'deliver_{uuid.uuid4().hex}.mp4'
                tmp_path = os.path.join(UPLOAD_DIR, tmp_name)
                try:
                    ok = _render_video(src, caption_text, tmp_path, font_sz, POS_Y, TEXT_STYLE)
                    if not ok:
                        errors += 1
                        continue
                    try:
                        _drive_upload(tmp_path, folder_id)
                        cur.execute("UPDATE captions SET times_used=times_used+1 WHERE id=?", (cap_id,))
                        cur.execute("UPDATE videos  SET times_used=times_used+1 WHERE id=?", (video_id,))
                        conn.commit()
                        uploaded += 1
                    except Exception:
                        errors += 1
                finally:
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except OSError:
                        pass

            results.append({'model': model_name, 'uploaded': uploaded, 'errors': errors})
            total_uploaded += uploaded
            total_errors   += errors

    finally:
        conn.close()

    return jsonify(results=results, total_uploaded=total_uploaded, total_errors=total_errors)


if __name__ == '__main__':

    import webbrowser

    import threading

    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5002')).start()

    app.run(debug=False, port=5002)


from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
import subprocess, os, uuid, shutil, json, sys, platform, functools

def _bundle_root():
    """Base directory: next to the .exe when bundled, or project folder in dev."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _resource(relative):
    """Bundled read-only resources (templates, binaries, fonts)."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)

if hasattr(sys, '_MEIPASS'):
    FFMPEG  = _resource('ffmpeg.exe')
    FFPROBE = _resource('ffprobe.exe')
elif platform.system() == 'Windows':
    FFMPEG  = 'ffmpeg'
    FFPROBE = 'ffprobe'
else:
    FFMPEG  = '/usr/bin/ffmpeg'
    FFPROBE = '/usr/bin/ffprobe'
if hasattr(sys, '_MEIPASS'):
    FONT_FILE = _resource('arialbd.ttf')
elif platform.system() == 'Windows':
    FONT_FILE = r'C:\Windows\Fonts\arialbd.ttf'
else:
    FONT_FILE = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'

app = Flask(__name__, template_folder=_resource('templates'))
app.secret_key = 'sntxt-s3cr3t-k3y-xK9mP2qR7vL4'

UPLOAD_DIR  = os.path.join(_bundle_root(), 'uploads')
OUTPUT_DIR  = os.path.join(_bundle_root(), 'outputs')
HOOKS_FILE  = os.path.join(_bundle_root(), 'hooks_library.txt')
USERS_FILE  = os.path.join(_bundle_root(), 'users.json')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _load_hooks():
    """Return the current hook library as an ordered list (preserving insertion order)."""
    if not os.path.exists(HOOKS_FILE):
        return []
    with open(HOOKS_FILE, 'r', encoding='utf-8') as f:
        return [ln.rstrip('\n') for ln in f if ln.strip()]

def _save_hooks(new_hooks):
    """Add new_hooks to the library, skipping duplicates. Returns (added, skipped)."""
    existing = _load_hooks()
    existing_set = {h.lower() for h in existing}
    added, skipped = 0, 0
    with open(HOOKS_FILE, 'a', encoding='utf-8') as f:
        for h in new_hooks:
            h = h.strip()
            if not h:
                continue
            if h.lower() in existing_set:
                skipped += 1
            else:
                f.write(h + '\n')
                existing_set.add(h.lower())
                added += 1
    return added, skipped

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
    """Split text into lines that fit within the video width."""
    avg_char_width = font_size * 0.58          # bold fonts are wider than 0.52
    usable_width = video_width * 0.88          # leave ~6% margin each side
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
        error = 'Invalid username or PIN — please try again.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login_page'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    f = request.files.get('video')
    if not f:
        return jsonify(error='No video'), 400
    uid = str(uuid.uuid4())
    ext = os.path.splitext(f.filename)[1] or '.mp4'
    path = os.path.join(UPLOAD_DIR, uid + ext)
    f.save(path)

    probe = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    vid = next(s for s in info['streams'] if s['codec_type'] == 'video')
    vw, vh = int(vid['width']), int(vid['height'])

    return jsonify(id=uid, ext=ext, width=vw, height=vh)

@app.route('/preview/<uid>')
@login_required
def preview(uid):
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(uid):
            return send_from_directory(UPLOAD_DIR, f)
    return '', 404

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    data = request.json
    uid = data['id']
    ext = data['ext']
    hooks = [h.strip() for h in data['hooks'] if h.strip()]
    pos_y = float(data.get('positionY', 0.5))
    font_pct = float(data.get('fontSizePct', 3))

    src = os.path.join(UPLOAD_DIR, uid + ext)
    if not os.path.exists(src):
        return jsonify(error='Video not found'), 404

    probe = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    vid = next(s for s in info['streams'] if s['codec_type'] == 'video')
    vw, vh = int(vid['width']), int(vid['height'])

    font_size = int((font_pct / 100) * vh)
    pad_v = max(int(font_size * 0.45), 4)
    line_h = int(font_size * 1.3)

    batch_id = str(uuid.uuid4())
    batch_dir = os.path.join(OUTPUT_DIR, batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    # Normalise font path for FFmpeg (forward slashes, escaped colon)
    font_ffmpeg = FONT_FILE.replace('\\', '/').replace(':', '\\:')

    files = []
    for i, hook in enumerate(hooks):
        lines = wrap_text(hook, font_size, vw)
        num_lines = len(lines)
        bar_h = num_lines * line_h + pad_v * 2

        bar_y = int(pos_y * vh - bar_h / 2)
        bar_y = max(0, min(vh - bar_h, bar_y))

        out_name = f"hook_{i+1}{ext}"
        out_path = os.path.join(batch_dir, out_name)

        vf_parts = [
            f"drawbox=y={bar_y}:x=0:w=iw:h={bar_h}:color=black@0.72:t=fill"
        ]
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

        subprocess.run([
            FFMPEG, '-y', '-i', src,
            '-vf', vf,
            '-codec:a', 'copy',
            '-preset', 'ultrafast',
            out_path
        ], capture_output=True)

        files.append(out_name)

    # Auto-save all used hooks to the library
    _save_hooks(hooks)

    return jsonify(batch=batch_id, files=files)

@app.route('/hooks/count')
@login_required
def hooks_count():
    return jsonify(count=len(_load_hooks()))

@app.route('/hooks/save', methods=['POST'])
@login_required
def hooks_save():
    data = request.json
    incoming = data.get('hooks', [])
    added, skipped = _save_hooks(incoming)
    return jsonify(added=added, skipped=skipped, total=len(_load_hooks()))

@app.route('/hooks/random')
@login_required
def hooks_random():
    import random
    n = int(request.args.get('n', 5))
    library = _load_hooks()
    if not library:
        return jsonify(hooks=[], total=0)
    chosen = random.sample(library, min(n, len(library)))
    return jsonify(hooks=chosen, total=len(library))

@app.route('/download/<batch>/<filename>')
@login_required
def download(batch, filename):
    d = os.path.join(OUTPUT_DIR, batch)
    return send_from_directory(d, filename, as_attachment=True)

@app.route('/download-all/<batch>')
@login_required
def download_all(batch):
    d = os.path.join(OUTPUT_DIR, batch)
    shutil.make_archive(d, 'zip', d)
    return send_from_directory(OUTPUT_DIR, batch + '.zip', as_attachment=True)

if __name__ == '__main__':
    import webbrowser, threading
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5001')).start()
    app.run(debug=False, port=5001)

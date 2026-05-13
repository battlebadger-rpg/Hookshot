"""
Standalone script: render Silvia videos with Clean-style text overlay.
Uses hookshot.db READ-ONLY. Does not modify any HookShot source files.
"""

import os
import json
import sqlite3
import subprocess

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(SCRIPT_DIR, 'HookShot', 'hookshot.db')
INPUT_DIR    = os.path.join(SCRIPT_DIR, 'new content updates', 'needs-text-overlay')
OUTPUT_DIR   = os.path.join(SCRIPT_DIR, 'new content updates', 'needs-text-overlay-rendered')

FFMPEG       = 'ffmpeg'
FFPROBE      = 'ffprobe'
FONT_INTER   = r'C:\Windows\Fonts\arialbd.ttf'

FONT_PCT     = 3.5
POS_Y        = 0.5
TEXT_STYLE   = 'clean'

# ── Helpers ──────────────────────────────────────────────────────────────────
def wrap_text(text, font_size, video_width):
    avg_char_width = font_size * 0.65
    usable_width   = video_width * 0.82
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


def _safe(line):
    # Escape backslashes first, then colons (FFmpeg drawtext requires \:), then quotes
    return line.replace("\\", "\\\\").replace("'", "\u2019").replace(":", "\\:")


def _ffmpeg_font(path):
    return path.replace('\\', '/').replace(':', '\\:')


def probe_video(src):
    """Return display dimensions (w, h) accounting for rotation metadata."""
    result = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src],
        capture_output=True, text=True, timeout=30,
    )
    info = json.loads(result.stdout)
    vid  = next(s for s in info['streams'] if s['codec_type'] == 'video')
    coded_w, coded_h = int(vid['width']), int(vid['height'])

    # Detect rotation from tags or display matrix side data
    rotation = 0
    if 'rotate' in vid.get('tags', {}):
        rotation = int(vid['tags']['rotate'])
    else:
        for sd in vid.get('side_data_list', []):
            if 'rotation' in sd:
                rotation = int(sd['rotation'])
                break

    # For 90/270° rotations FFmpeg auto-rotates so the processed frame is portrait
    if abs(rotation) in (90, 270):
        return coded_h, coded_w   # swap: display width=coded_h, display height=coded_w
    return coded_w, coded_h


def render_clean(src_path, caption_text, out_path, font_size, pos_y=0.5):
    """Render src_path with clean-style overlay to out_path. Returns True on success."""
    vw, vh      = probe_video(src_path)
    lines       = wrap_text(caption_text, font_size, vw)
    font_ffmpeg = _ffmpeg_font(FONT_INTER)
    line_h      = int(font_size * 1.35)
    total_h     = len(lines) * line_h
    start_y     = max(0, int(pos_y * vh - total_h / 2))

    vf_parts = []
    for j, line in enumerate(lines):
        line_y = start_y + j * line_h
        vf_parts.append(
            f"drawtext=fontfile='{font_ffmpeg}':text='{_safe(line)}'"
            f":fontcolor=white:fontsize={font_size}"
            f":x=(w-tw)/2:y={line_y}"
            f":borderw=2:bordercolor=black@0.9"
        )

    vf = ','.join(vf_parts)
    # No -noautorotate: let FFmpeg apply rotation so frames are portrait before drawtext.
    # No -metadata:s:v:0 rotate=0: output inherits correct orientation naturally.
    r = subprocess.run([
        FFMPEG, '-y', '-i', src_path,
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '28',
        '-c:a', 'copy',
        out_path,
    ], capture_output=True)
    return r.returncode == 0, r.stderr.decode(errors='replace')[-800:] if r.returncode != 0 else ''


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Collect input videos
    video_files = sorted(
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(('.mp4', '.mov'))
    )
    print(f"Input videos found: {len(video_files)}")

    # Read-only DB: fetch least-used Silvia captions
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, caption, times_used FROM captions
        WHERE COALESCE(active,1)=1
        AND (models='' OR models IS NULL
             OR (',' || REPLACE(models,';',',') || ',') LIKE ('%,' || 'Silvia' || ',%'))
        ORDER BY times_used ASC, id ASC
    """)
    captions = cur.fetchall()
    conn.close()

    print(f"Silvia captions available: {len(captions)}")

    if len(captions) < len(video_files):
        print(f"WARNING: only {len(captions)} captions for {len(video_files)} videos — some will repeat")

    success, failures = 0, []

    for i, filename in enumerate(video_files):
        cap_id, cap_text, cap_used = captions[i % len(captions)]
        src  = os.path.join(INPUT_DIR, filename)
        # Keep original filename, change extension to .mp4
        base = os.path.splitext(filename)[0]
        out  = os.path.join(OUTPUT_DIR, base + '.mp4')

        try:
            _, vh   = probe_video(src)
            font_sz = int(FONT_PCT / 100 * vh)
            ok, err = render_clean(src, cap_text, out, font_sz, POS_Y)
        except Exception as e:
            ok, err = False, str(e)

        status = "OK" if ok else "FAIL"
        print(f"[{i+1:02d}/{len(video_files)}] {filename} -> {base}.mp4 | cap={cap_id} (used={cap_used}) | {status}")
        if ok:
            success += 1
        else:
            failures.append((filename, cap_id, err))
            print(f"         ERROR: {err[:200]}")

    print()
    print(f"=== DONE: {success}/{len(video_files)} rendered successfully ===")
    if failures:
        print(f"Failures ({len(failures)}):")
        for fname, cid, err in failures:
            print(f"  {fname} (cap {cid}): {err[:120]}")


if __name__ == '__main__':
    main()

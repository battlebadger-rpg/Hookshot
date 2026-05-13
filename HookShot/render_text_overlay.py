"""
render_text_overlay.py — Standalone text overlay renderer using HookShot caption library.

Usage:
    python render_text_overlay.py --input "path/to/videos" --output "path/to/rendered" --model Silvia

Reads captions from hookshot.db (read-only). Picks least-used captions for the given model.
Renders Clean style: Inter Bold (Arial Bold on Windows), white text, thin black outline.
Handles phone videos with rotation metadata (iPhone 90/270-degree rotation).
"""

import argparse
import json
import os
import platform
import sqlite3
import subprocess
import sys


# ── Font paths ────────────────────────────────────────────────────────────────
if platform.system() == 'Windows':
    FONT_INTER = r'C:\Windows\Fonts\arialbd.ttf'
else:
    FONT_INTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts', 'Inter-Bold.ttf')

FFMPEG  = 'ffmpeg'
FFPROBE = 'ffprobe'

FONT_PCT = 3.5   # font size as % of display height
POS_Y    = 0.5   # vertical centre of text block (0.0 = top, 1.0 = bottom)


# ── Text helpers ──────────────────────────────────────────────────────────────
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
    """Escape special characters for FFmpeg drawtext filter."""
    # Order matters: escape backslashes first, then other special chars
    return line.replace('\\', '\\\\').replace("'", '\u2019').replace(':', '\\:')


def _ffmpeg_font(path):
    """Convert font path to FFmpeg-compatible format."""
    return path.replace('\\', '/').replace(':', '\\:')


# ── Video probe ───────────────────────────────────────────────────────────────
def probe_video(src):
    """
    Return display dimensions (width, height) accounting for rotation metadata.
    Phone videos (e.g. iPhone portrait) are often stored as landscape with a 90°
    rotation flag — this returns the post-rotation display size so font size and
    text position calculations are correct.
    """
    result = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_streams', src],
        capture_output=True, text=True, timeout=30,
    )
    info = json.loads(result.stdout)
    vid  = next(s for s in info['streams'] if s['codec_type'] == 'video')
    coded_w, coded_h = int(vid['width']), int(vid['height'])

    # Check rotation in stream tags or display matrix side data
    rotation = 0
    if 'rotate' in vid.get('tags', {}):
        rotation = int(vid['tags']['rotate'])
    else:
        for sd in vid.get('side_data_list', []):
            if 'rotation' in sd:
                rotation = int(sd['rotation'])
                break

    # For 90/270° rotations FFmpeg auto-rotates during decode, so the frame
    # the vf filter sees has swapped dimensions
    if abs(rotation) in (90, 270):
        return coded_h, coded_w
    return coded_w, coded_h


# ── Renderer ──────────────────────────────────────────────────────────────────
def render_clean(src_path, caption_text, out_path, font_size, pos_y=0.5):
    """
    Apply Clean-style text overlay to src_path and write to out_path.
    Clean style: Inter/Arial Bold, white text, thin black outline, no background bar.
    Returns (success: bool, error_snippet: str).
    """
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
    # No -noautorotate: FFmpeg applies rotation before the vf filter so drawtext
    # operates on the correctly-oriented frame.
    r = subprocess.run([
        FFMPEG, '-y', '-i', src_path,
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '28',
        '-c:a', 'copy',
        out_path,
    ], capture_output=True)

    if r.returncode != 0:
        return False, r.stderr.decode(errors='replace')[-800:]
    return True, ''


# ── Caption lookup ────────────────────────────────────────────────────────────
def load_captions(db_path, model_name):
    """
    Return list of (id, caption, times_used) for model_name, ordered least-used first.
    Opens hookshot.db read-only.
    """
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, caption, times_used FROM captions
        WHERE COALESCE(active, 1) = 1
          AND (
            models = '' OR models IS NULL
            OR (',' || REPLACE(models, ';', ',') || ',') LIKE ('%,' || ? || ',%')
          )
        ORDER BY times_used ASC, id ASC
    """, (model_name,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Render text overlays onto videos using HookShot caption library.'
    )
    parser.add_argument('--input',  required=True, help='Folder containing input videos')
    parser.add_argument('--output', required=True, help='Folder for rendered output videos')
    parser.add_argument('--model',  required=True, help='Model name to pull captions for (e.g. Silvia)')
    args = parser.parse_args()

    input_dir  = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    model_name = args.model.strip()

    if not os.path.isdir(input_dir):
        print(f"ERROR: input folder not found: {input_dir}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Locate hookshot.db relative to this script
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hookshot.db')
    if not os.path.isfile(db_path):
        print(f"ERROR: hookshot.db not found at: {db_path}")
        sys.exit(1)

    # Collect input videos
    video_files = sorted(
        f for f in os.listdir(input_dir)
        if f.lower().endswith(('.mp4', '.mov'))
    )
    if not video_files:
        print(f"No .mp4/.mov files found in: {input_dir}")
        sys.exit(1)

    print(f"Input videos : {len(video_files)}")

    # Load captions
    captions = load_captions(db_path, model_name)
    if not captions:
        print(f"ERROR: no active captions found for model '{model_name}' in hookshot.db")
        sys.exit(1)

    print(f"Captions ({model_name}): {len(captions)} available")
    if len(captions) < len(video_files):
        print(f"WARNING: fewer captions than videos — captions will repeat")

    success, failures = 0, []

    for i, filename in enumerate(video_files):
        cap_id, cap_text, cap_used = captions[i % len(captions)]
        src  = os.path.join(input_dir, filename)
        base = os.path.splitext(filename)[0]
        out  = os.path.join(output_dir, base + '.mp4')

        try:
            _, vh   = probe_video(src)
            font_sz = int(FONT_PCT / 100 * vh)
            ok, err = render_clean(src, cap_text, out, font_sz, POS_Y)
        except Exception as e:
            ok, err = False, str(e)

        status = 'OK' if ok else 'FAIL'
        print(f"[{i+1:02d}/{len(video_files)}] {filename} -> {base}.mp4  cap={cap_id} (used={cap_used})  {status}")
        if ok:
            success += 1
        else:
            failures.append((filename, cap_id, err))
            print(f"         ERROR: {err[:200]}")

    print()
    print(f"=== DONE: {success}/{len(video_files)} rendered successfully ===")
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for fname, cid, err in failures:
            print(f"  {fname} (cap {cid}): {err[:120]}")
    sys.exit(0 if not failures else 1)


if __name__ == '__main__':
    main()

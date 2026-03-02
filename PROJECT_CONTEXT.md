# HookShot — Project Context Document

> **Purpose of this file:** Drop this into a new Cursor chat to give the agent full context of the project without needing to re-explain anything.

---

## What is HookShot?

HookShot is a web-based video tool that overlays hook text onto videos. Users upload a video, type multiple text hooks (one per line), and the tool generates a separate output video for each hook with the text burned onto the video using FFmpeg. It is used to add viral-style text hooks to Reels/TikTok videos to boost engagement.

The tool was originally called "SnapText" (from a friend's code) and was rebranded to **HookShot** during development.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3 / Flask |
| Video processing | FFmpeg (via subprocess) |
| Production server | Gunicorn (WSGI) |
| Reverse proxy | Nginx |
| Process manager | systemd |
| SSL | Let's Encrypt / Certbot |
| SSH/deployment | paramiko (Python library) |
| Packaging (Windows) | PyInstaller |

---

## Live Server

| Item | Value |
|------|-------|
| Provider | Hetzner VPS |
| OS | Ubuntu 24.04 |
| IP | 5.223.69.224 |
| Root password | EWL7ktAMeFrU |
| Live URL | https://snaptext.kira-dashie.com |
| App directory | /root/snaptext/ |
| Systemd service | snaptext |
| Nginx config | /etc/nginx/sites-available/snaptext |
| SSL cert | /etc/letsencrypt/live/snaptext.kira-dashie.com/ |
| DNS | Cloudflare (A record: snaptext → 5.223.69.224, grey cloud / DNS only) |
| Existing app on same server | /root/content-stage-tool/ (Node.js, port 3000, PM2) |

### Useful server commands
```bash
systemctl status snaptext          # check service status
systemctl restart snaptext         # restart after file changes
journalctl -u snaptext -n 50 --no-pager   # view logs
```

### Deploying updates to live server
Use `push_update.py` in the project folder — it SSHes in via paramiko, uploads changed files, and restarts the service:
```powershell
python push_update.py
```

---

## Local Development

| Item | Value |
|------|-------|
| Project folder | `d:\AI tools\snap text tool\Snapchat Text on Screen\` |
| Start local server | double-click `start.bat` OR run `python app.py` |
| Local URL | http://localhost:5001 |
| FFmpeg | Already installed system-wide, on PATH |
| Python | 3.13 |

The server auto-opens the browser after 1.5 seconds when run via `python app.py` directly.

---

## Project File Structure

```
Snapchat Text on Screen/
├── app.py                  # Main Flask application (all backend logic)
├── users.json              # Login credentials (username → PIN)
├── hooks_library.txt       # Shared hook library (one hook per line, auto-grows)
├── requirements.txt        # Just "flask"
├── start.bat               # Local launcher (double-click to start)
├── snaptext.spec           # PyInstaller build spec
├── deploy.py               # Full first-time deployment script (SSH via paramiko)
├── push_update.py          # Quick update pusher (upload files + restart service)
├── check_server.py         # Server diagnostics script
├── PROJECT_CONTEXT.md      # This file
├── templates/
│   ├── index.html          # Main app UI
│   └── login.html          # Login page
├── uploads/                # Uploaded videos (auto-created)
├── outputs/                # Generated videos (auto-created)
└── dist/
    └── SnapText/           # PyInstaller Windows exe package
        ├── SnapText.exe
        ├── Start SnapText.bat
        └── _internal/      # Bundled dependencies
```

---

## app.py — Key Architecture

### Path helpers
- `_bundle_root()` — returns the directory next to the .exe (bundled) or project folder (dev). Used for writable data (uploads, outputs, hooks, users).
- `_resource(relative)` — returns path to read-only bundled resources (templates, ffmpeg.exe, font). Uses `sys._MEIPASS` when bundled.

### Cross-platform FFmpeg & font paths
```python
# FFmpeg/FFprobe
if bundled:   ffmpeg.exe / ffprobe.exe from bundle
elif Windows: 'ffmpeg' / 'ffprobe'  (system PATH)
else:         '/usr/bin/ffmpeg' / '/usr/bin/ffprobe'  (Linux full path — needed because systemd has restricted PATH)

# Font
if bundled:   arialbd.ttf from bundle
elif Windows: C:\Windows\Fonts\arialbd.ttf
else:         /usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf
```

**IMPORTANT:** The font path is stored as a plain Windows path and normalised for FFmpeg in the generate function:
```python
font_ffmpeg = FONT_FILE.replace('\\', '/').replace(':', '\\:')
```
Do NOT pre-format FONT_FILE with `\:` — the normalisation code will break it.

**IMPORTANT:** On Linux (systemd), always use full paths for ffmpeg/ffprobe (`/usr/bin/ffmpeg`), not just `'ffmpeg'`, because systemd runs with a restricted PATH that doesn't include /usr/bin.

### Login system
- Sessions via Flask's built-in session (cookie-based)
- `app.secret_key = 'sntxt-s3cr3t-k3y-xK9mP2qR7vL4'`
- Users stored in `users.json` — format: `{"username": "PIN"}`
- `login_required` decorator protects all routes except `/login` and `/logout`
- Usernames are lowercased on login

### Text rendering (FFmpeg)
- Uses `drawbox` for the semi-transparent black bar background
- Uses one `drawtext` per wrapped line (NOT `\n` in text — FFmpeg filter parser consumes the backslash, causing the letter 'n' to appear literally)
- `wrap_text()` function calculates chars per line based on `font_size * 0.52` avg char width
- Bar height is dynamic: `num_lines * line_h + pad_v * 2`

### Hook library
- Stored as plain text file: `hooks_library.txt`, one hook per line
- Deduplication is case-insensitive
- Auto-saves all hooks used in Generate Videos
- Shared across all users (single file on server)

---

## API Routes

| Route | Method | Auth | Description |
|-------|--------|------|-------------|
| `/login` | GET/POST | No | Login page |
| `/logout` | GET | No | Clears session |
| `/` | GET | Yes | Main app UI |
| `/upload` | POST | Yes | Upload video, returns id/ext/width/height |
| `/preview/<uid>` | GET | Yes | Serve uploaded video for preview |
| `/generate` | POST | Yes | Generate videos, auto-saves hooks |
| `/hooks/count` | GET | Yes | Returns library hook count |
| `/hooks/save` | POST | Yes | Add hooks to library (deduped) |
| `/hooks/random` | GET | Yes | Returns ?n= random hooks from library |
| `/download/<batch>/<filename>` | GET | Yes | Download single output video |
| `/download-all/<batch>` | GET | Yes | Download all outputs as .zip |

---

## Users & Credentials

| Username | PIN |
|----------|-----|
| todd | 1981 |
| connor | 4726 |
| niomi | 3851 |
| arra | 6293 |
| melissa | 7412 |
| melanie | 5038 |
| cynthia | 8164 |
| gine | 2947 |
| rowena | 6381 |
| guest | 1573 |

To add/change users: edit `users.json` locally and run `push_update.py` to deploy.

---

## UI — Colour Scheme (HookShot brand)

| Element | Colour |
|---------|--------|
| Primary blue (buttons, accents, logo) | `#38bdf8` (sky-400) |
| Button hover | `#7dd3fc` (lighter sky) |
| Disabled buttons | `#e0e0e0` / `#aaa` text |
| Background | `#f8f8f8` |
| Cards | `#fff` with `#e8e8e8` border |
| Body text | `#1a1a1a` |
| Recommendation tip box | `#fefce8` bg / `#fef08a` border / `#713f12` text |
| Progress bar | `#38bdf8` |
| Slider accent | `#38bdf8` |

---

## Known Issues Fixed (history)

1. **Font not found on Windows** — `Helvetica Neue` doesn't exist on Windows. Fixed by using `fontfile=` with full path to Arial Bold / Liberation Sans Bold instead of `font=` with a name.

2. **Text not wrapping** — FFmpeg `drawtext` doesn't wrap text. Fixed by using Python to pre-wrap text and issuing one `drawtext` filter per line.

3. **`\n` appearing literally in output** — Using `\n` in FFmpeg filter text causes the backslash to be consumed by the filter parser, printing the letter `n`. Fixed by separate `drawtext` per line.

4. **ffprobe not found on Linux** — systemd service has a restricted PATH. Fixed by using `/usr/bin/ffprobe` and `/usr/bin/ffmpeg` full paths on Linux.

5. **Font path normalisation bug** — FONT_FILE was pre-formatted with `\:` which then got double-processed by the normalisation code. Fixed by storing as plain Windows path and normalising once in generate().

6. **Unicode print errors in deploy scripts** — Terminal uses cp1252 encoding. Fixed by encoding output as ASCII with error replacement.

---

## Planned / Potential Next Features

1. **Multi-video upload with random pairing** — Upload multiple videos (e.g. 5), enter many hooks, and the tool randomly pairs each hook with a video to generate N outputs. Original plan was to add a "number of outputs" input.

2. **Text style customisation** — Change font, colour, outline vs shadow, bar opacity, bar style. Currently hard-coded in `app.py` generate() function.

3. **Admin page** — Simple web UI to manage users and view/delete hooks in the library without touching files directly.

4. **Cleanup script** — Uploads and outputs accumulate on the server. A cron job or manual cleanup endpoint to delete old files.

5. **Windows .exe update** — The PyInstaller exe in `dist/SnapText/` was built before the login system and hook library were added. It needs to be rebuilt to include all current features. Run `pyinstaller snaptext.spec` in the project folder.

---

## How to Deploy Changes

### To live server (quick update)
```powershell
# Edit files locally, then:
python push_update.py
```

### To rebuild Windows exe
```powershell
pyinstaller snaptext.spec
# Output goes to dist/SnapText/
# Zip dist/SnapText/ and distribute
```

### To run locally
```powershell
# Option 1 - double click start.bat
# Option 2:
cd "d:\AI tools\snap text tool\Snapchat Text on Screen"
python app.py
# Opens http://localhost:5001 automatically
```

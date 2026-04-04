import subprocess, urllib.request, urllib.error, json, uuid, os

TOKEN  = "8549015220:AAGzRPdl_mg9Nv-Y6kj-cwxX78ZY-P8wzxk"
FFMPEG = "/usr/bin/ffmpeg"
FONT   = "/root/hookshot/HookShot/fonts/Inter-Bold.ttf"
SRC    = "/root/hookshot/HookShot/library_videos/V59.mp4"
OUT    = "/tmp/hookshot_test_send.mp4"
CHAT   = "-1003600023738"
TOPIC  = "4"

# 1. Render
vf = "drawtext=fontfile='" + FONT + "':text='HookShot test':fontcolor=white:fontsize=54:x=(w-tw)/2:y=(h-th)/2:borderw=2:bordercolor=black@0.9"
r = subprocess.run([FFMPEG, "-y", "-i", SRC, "-vf", vf, "-codec:a", "copy", "-preset", "ultrafast", OUT], capture_output=True)
size = os.path.getsize(OUT) if os.path.exists(OUT) else 0
print("Render rc=" + str(r.returncode) + " size=" + str(size) + " bytes")
if r.returncode != 0:
    print("FFMPEG ERR:", r.stderr.decode()[-200:])
    exit()

# 2. Send
with open(OUT, "rb") as f:
    video_data = f.read()

boundary = "TGB" + uuid.uuid4().hex
crlf = b"\r\n"
parts = []
for k, v in [("chat_id", CHAT), ("message_thread_id", TOPIC), ("supports_streaming", "true")]:
    parts.append(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + k + "\"\r\n\r\n" + v).encode())
parts.append(
    ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"video\"; filename=\"test.mp4\"\r\nContent-Type: video/mp4\r\n\r\n").encode()
    + video_data
)
parts.append(("--" + boundary + "--").encode())
body = crlf.join(parts)

req = urllib.request.Request(
    "https://api.telegram.org/bot" + TOKEN + "/sendVideo",
    data=body,
    headers={"Content-Type": "multipart/form-data; boundary=" + boundary}
)
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
        print("SEND OK:", result.get("ok"), "msg_id:", result.get("result", {}).get("message_id"))
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code, e.read().decode()[:400])
except Exception as e:
    print("ERROR:", str(e))

if os.path.exists(OUT):
    os.remove(OUT)

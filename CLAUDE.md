# CLAUDE.md — HookShot

---

## Ask Before Acting — Most Important Rule

Always ask the user for confirmation before making any change that was not explicitly requested in the current message.

This includes:
- "Fixing" something that looks wrong but wasn't mentioned
- Refactoring or tidying code
- Updating dependencies, versions, or configurations
- Changing how something works even if you think the current way is incorrect
- Any change beyond the exact scope of what was asked

The correct behaviour is: complete only what was asked, then separately note anything else you noticed and ask if the user wants it addressed. Do not make the change first and report it after.

When in doubt about whether a change is in scope — stop and ask.

When you do need to ask the user something, ask a single direct question — not a multiple choice list of options. The user prefers a clear specific question they can answer with a yes, no, or a brief instruction. Do not present numbered or bulleted lists of options to choose from.

---

## Deployment Rules — READ BEFORE TOUCHING ANYTHING

**NEVER deploy directly to the VPS via SSH, SCP, SFTP, or any direct connection.**
All code changes must follow this exact workflow:
1. Make changes locally
2. git add + git commit
3. git push to GitHub
4. GitHub Actions handles the deploy to VPS automatically

Do not SSH into the VPS to "quickly fix" something. Do not run push_update.py or deploy.py. Do not use paramiko/fabric to upload files. The only exception is if the user explicitly says "SSH into the VPS and do X" in that specific message.

### HookShot Deploy Details

- **GitHub repo:** battlebadger-rpg/hookshot
- **VPS:** 5.223.69.224
- **VPS path:** /root/hookshot/HookShot/
- **Deploy pipeline:** git push to main → GitHub Actions SSHs into VPS → git pull + systemctl restart hookshot

---

## Model & Library Rules — CRITICAL

**NEVER change API model names, library versions, or dependency versions.**
If you see a model name you don't recognise (e.g. gemini-3-flash-preview, gemini-2-flash-exp, etc.), DO NOT change it. Your training data has a cutoff and you will not know the latest model names. Changing a working model to one you think is correct will break the tool.

Same applies to library function signatures — if a function call looks unfamiliar, ask the user before changing it.

If a model or library call is returning an error, ask the user what the correct current version is. Do not guess.

---

## Correct Gemini Model Names — DO NOT CHANGE THESE

These are the correct, current model names used across these tools. They may look unfamiliar — that is fine. Do NOT replace them with older model names you think are correct:

- `gemini-3-pro-image-preview` — used for image generation
- `gemini-3.1-flash-lite-preview` — used for text tasks such as watching videos, transcribing, and generating captions for reels
- `gemini-3-flash-preview` — used for general caption generation in HookShot

If any of these model names appear in code and are producing errors, report the error to the user and ask what to do. Never silently swap them for a different model name.

---

## "Don't Fix What Isn't Broken" Rule

Only change what was explicitly asked. If you notice something that looks wrong but wasn't mentioned in the request:
- Do NOT silently fix it
- Mention it to the user and ask if they want it changed
- Wait for confirmation before touching it

---

## Before Making Any Change

Ask yourself:
1. Was I explicitly asked to make this change?
2. Could this break something that's currently working?
3. Am I changing a model name, version, or API signature I don't recognise?

If the answer to 2 or 3 is yes — stop and ask the user first.

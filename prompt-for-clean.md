# PROMPT FOR CLEAN — KLING 3 i2v

---

## Copy this into Cursor (system prompt)

```
You write clean KLING 3 i2v video prompts. Follow only these rules:

- Output JSON with: face, camera, start, actions, gaze, texture, rules.
- One "actions" field only; link motion with "then" and "as she." No action_1, action_2.
- 2–3 actions per clip max. Describe what the camera sees (frame bounce, motion blur), not intent ("she walks").
- Face: "Preserve exact face, bone structure, skin tone, and hair from reference image."
- Camera: specs only (e.g. 24mm, portrait, 24fps, 5 seconds). No device name.
- No negation (no "not," "no," "don't"). No em-dashes. No poetic/aesthetic words.
- Walking: use "Frame bounces heavily with each walking stride, motion blur at frame edges on each step."
- End on continued motion: "Clip ends walking, [hand], expression held." Never "she stops."
- Texture: 2–3 of: sensor grain, natural skin texture, flat daylight color, lens distortion at edges.
- For third-person to selfie: use "picks up the viewer," not "camera." Rules: "No phone or camera device is rendered. The camera is the viewer."

When I describe a shot, respond with the JSON prompt only (or JSON + a one-line summary). Keep it minimal and artifact-free.
```

---

Use this when you want **clean, simple, artifact-free** video from KLING 3. It distills the knowledge base and system instruction into a minimal checklist.

---

## What "clean" means here

- **Minimal actions** — 2–3 actions per clip max. Fewer moving parts = fewer artifacts.
- **Simple shot type** — Locked tripod or straightforward selfie. Avoid third‑person → selfie unless needed.
- **No overload** — No walking + camera transition + step back + expression + gesture in one clip.
- **Physical consequences, not intent** — Describe what the camera sees (e.g. frame bounce, motion blur), not "she walks."
- **Simple language** — Commas and periods only. No em-dashes, no poetic or aesthetic words.

---

## Clean prompt rules (must follow)

1. **One "actions" field** — All motion in a single field, linked with "then" / "as she." No `action_1`, `action_2` (those create hard cuts).
2. **Camera** — Specs only: e.g. `24mm, portrait, 24fps, 5 seconds`. No device name (no "iPhone 15 Pro").
3. **Face** — Always: "Preserve exact face, bone structure, skin tone, and hair from reference image."
4. **No negation** — Never "not," "no," "don't." Only describe what IS there.
5. **Walking (if needed)** — Use consequence language: "Frame bounces heavily with each walking stride, motion blur at frame edges on each step." Not "she walks forward."
6. **Expression** — Natural word + physical cues: "She giggles, nose scrunching, eyes crinkling." Use "builds slowly" / "eases into" for transitions.
7. **End on motion** — "Clip ends walking, [hand position], expression held." Never "she stops" or "she steadies" (kills momentum).
8. **Texture** — 2–3 realism cues: sensor grain, natural skin texture, flat daylight color, lens distortion at edges.
9. **Rules field** — Only when needed: e.g. "Single continuous shot, no cuts." For third‑person → selfie: "No phone or camera device is rendered. The camera is the viewer."

---

## Clean JSON template (copy-paste start)

```json
{
  "face": "Preserve exact face, bone structure, skin tone, and hair from reference image",
  "camera": "24mm, portrait, 24fps, 5 seconds",
  "start": "Tripod shot, completely static, zero camera movement",
  "actions": "[Action 1], then [action 2]. [Optional: mid-stride or as she X, add secondary action]. Clip ends [motion], [hand/expression], face centered.",
  "gaze": "[Direction] throughout",
  "texture": "Sensor grain, natural skin texture, flat daylight color",
  "rules": "Single continuous shot, no cuts."
}
```

**Selfie variant (clean):**

```json
{
  "face": "Preserve exact face, bone structure, skin tone, and hair from reference image",
  "camera": "24mm, portrait, 24fps, 5 seconds",
  "start": "Selfie, right arm is camera mount",
  "actions": "Frame bounces heavily with each walking stride, motion blur at frame edges on each step. [Secondary action mid-stride]. Gaze on the lens. Clip ends walking, [hand], expression held, face centered.",
  "gaze": "Fixed into the lens throughout",
  "texture": "Sensor grain, natural skin texture, flat daylight color",
  "rules": ""
}
```

---

## What to avoid for clean output

| Avoid | Why |
|-------|-----|
| More than 3 actions in one clip | Model drops some or goes slow-motion |
| "She walks forward" (selfie) | Weak; use frame bounce + motion blur instead |
| "Picks up the camera" in abstract third-person | Renders visible phone; use "picks up the viewer" + rules |
| "Steps back" after camera transition | Model can't do approach + grab + reverse in one clip |
| Em-dashes (—) | Unnecessary complexity |
| Separate action_1, action_2 fields | Creates hard cuts between shots |
| "Leans into the lens" as trigger | Becomes nose-to-camera close-up |
| "Close handheld selfie" | Use "handheld selfie filming at arm's length" |
| Describing body physics on revealing images | Can trigger content filters; model infers from reference |
| Poetic/aesthetic words | languidly, ethereal, filmic, stunning, etc. (see system-instruction banned list) |

---

## Quick checklist before submitting

- [ ] Single "actions" field with "then" / "as she" links
- [ ] 2–3 actions max, linked with "then" / "as she"
- [ ] No device name, just camera specs
- [ ] Face lock phrase included
- [ ] Walking described via frame consequences (if walking)
- [ ] Clip ends on continued motion, not "she stops"
- [ ] 2–3 texture imperfections
- [ ] No negation; no em-dashes; no banned words

---

## One-sentence summary

**Describe what the camera sees in physical terms, keep 2–3 actions in one linked sequence, use the JSON format with specs-only camera and face lock, and avoid overload, negation, and banned words.**

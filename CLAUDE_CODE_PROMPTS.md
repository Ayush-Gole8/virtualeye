# Virtual Eye 3.0 — Claude Code Implementation Prompts (P1–P6)

**Companion to:** `CODEBASE_AUDIT.md`
**Written:** 2026-08-16
**Decisions baked in:** implement all of P1–P6; clock-face wording (P3) applies in **priority mode only** so the naive baseline stays intact for the study.

---

## How to use this file

1. **Initialize Claude Code at the repository root** — the folder that contains both `src/` and `backend/`. All paths below are relative to that root.
2. **Run one prompt per Claude Code session.** Start a fresh session (or `/clear`) between prompts so context stays clean and diffs stay small.
3. **Paste a whole fenced block** (the `GOAL … VERIFY` text) as a single message. Each block is self-contained — it tells Claude Code what to read, what to change, what *not* to touch, and how to check itself.
4. **After each prompt:** review the diff, run the VERIFY steps, then commit before moving on (e.g. `git commit -am "P1: wire agility + session_id"`). If a check fails, tell Claude Code exactly which one — don't move to the next prompt.
5. **Servers:** backend = `cd backend && python server.py` (venv at `backend/.venv`); frontend = `npm run dev`.

**Recommended order:** P1 → P2 (both are frontend and share the settings context + request path) → P3 → P4 → P5 → P6. P3/P4/P5 are independent; do P6 last so cleanup lands on stable code.

### Shared backend contract (already implemented — do not rebuild)

`POST /analyze_frame` currently **receives** `frame`, `lang`, `mode` and already **reads but never receives** `session_id` and `agility` (`"high"|"low"`, default `"high"`; `"low"` = more cautious = earlier warnings).

It **returns** JSON with: `detections[]` (each has `class`, `side` ∈ `left|center|right`, `cx` px, `distance` m, `distance_str`, `bbox`, `track_id`, `motion`, `ttc`, `priority`, and `urgency` ∈ `none|low|medium|high|critical`), plus `speech`, `mode`, `agility`, `path`, `overhead`, `dropoff`, `staircase`, and `alerts[]` (each `{ type: dropoff|overhead|staircase, priority: critical|high, speech, distance_m, confidence }`), `has_objects`, `annotated_image`, `K_value`.

Today the frontend uses only `speech`, `detections`, `annotated_image` — and also reads `data.caption` / `data.wall_alert`, which the backend never sends (dead reads, cleaned up in P6).

---

## PROMPT 1 — Reach the backend's agility personalization (unlocks §3.3 / §3.7)

*Frontend only. The backend already honours `agility` and `session_id`; the UI just never sends them.*

```text
GOAL
Add a user setting for "agility" and send it (plus the existing session_id) with every
/analyze_frame request, so the backend's already-built TTC personalization becomes reachable.
Default must stay "high" so nothing changes until the user opts in.

FILES
- src/context/ModeContext.jsx      (READ — this is the context pattern to copy)
- src/context/SettingsContext.jsx  (CREATE)
- src/main.jsx or src/App.jsx       (wrap app with the new provider, wherever ModeProvider is mounted)
- src/pages/VisionPage.jsx          (send the fields; add an agilityRef like the existing modeRef)
- the component that renders the Priority/Naive toggle (search src/components/layout/DashboardLayout.jsx
  and src/pages/DashboardHome.jsx) — add the agility control next to it

CONTEXT
- Backend /analyze_frame reads form field `agility` ("high"|"low", default "high") and `session_id`.
  The frontend currently sends only frame, lang, mode.
- ModeContext.jsx shows the house pattern: useState + a window CustomEvent bridge + a useX() hook.
- In VisionPage.jsx the periodic loop reads modeRef.current / langRef.current (refs) to avoid stale
  closures. It already computes a session_id that it sends to /question and /reset — find that exact
  variable and reuse it; do NOT invent a new id.

IMPLEMENT
1. Create src/context/SettingsContext.jsx modeled on ModeContext.jsx:
   - state: agility ∈ 'high'|'low', default 'high'
   - persist to localStorage key 've_agility' (read on init, write on change)
   - listen for a 'voice-set-agility' CustomEvent (parity with voice-set-mode)
   - export a useSettings() hook returning { agility, setAgility }
2. Mount <SettingsProvider> alongside <ModeProvider> (same file/spot ModeProvider is used).
3. In VisionPage.jsx: import useSettings; add an agilityRef synced via useEffect (mirror modeRef).
   In analyzeFrame(), append to the FormData: 'agility' = agilityRef.current, and 'session_id' =
   the existing session id variable already sent to /question and /reset.
4. Add a small control by the Priority/Naive toggle: label "Mobility", options "Fast" (agility=high)
   and "Cautious" (agility=low), wired to setAgility, with an aria-label.

CONSTRAINTS
- Frontend only. Do not modify anything under backend/.
- Keep it minimal and match ModeContext's style. Default stays 'high'. Don't rename existing vars.

VERIFY
- grep shows `agility` in src/context/SettingsContext.jsx and in the analyzeFrame FormData in
  src/pages/VisionPage.jsx.
- With both servers running, DevTools > Network: an /analyze_frame request includes agility and
  session_id; after choosing "Cautious" the JSON response shows "agility":"low".
- Choose Cautious, reload the page → still Cautious (localStorage).
- Change mode/agility mid-run → the next request reflects it (no stale closure).
```

---

## PROMPT 2 — Non-speech cues from `alerts[]` / `urgency` (§3.5)

*Frontend only. Do PROMPT 1 first — this reuses the settings area and the same request path.*

```text
GOAL
Turn the backend's structured output into non-speech cues: a stereo-panned earcon plus a vibration
pattern whose intensity matches severity. Additive to speech, never a replacement.

FILES
- src/pages/VisionPage.jsx   (loop, response handling, Start/Stop)
- src/lib/cues.js            (OPTIONAL helper for the earcon/vibration logic)

CONTEXT (response fields already returned by /analyze_frame)
- alerts[]: { type: 'dropoff'|'overhead'|'staircase', priority: 'critical'|'high', speech,
  distance_m, confidence }  (structural hazards — treat as "ahead")
- detections[]: each has side ('left'|'center'|'right'), cx (px; frame width is 480), and
  urgency ('none'|'low'|'medium'|'high'|'critical')
- The loop runs about every 2500 ms and RE-SENDS the same alerts/urgency while the condition
  persists, so cues MUST be de-duplicated or they repeat every cycle.
- Reuse existing guards: isSpeechMuted(), qaInProgressRef.current, qaModeRef.current.
- There is a Start action (user gesture) that begins the camera/loop — the only safe place to
  create/resume a Web Audio context.

IMPLEMENT
1. Lazily create ONE AudioContext on Start (user gesture) and call resume(); keep it in a ref;
   close it on Stop. Never create it at module load.
2. Per frame, compute a single cue = the highest severity present: map alert.priority
   (critical>high) and detection.urgency (critical>high>medium; ignore low/none) to a shared rank.
   If nothing reaches medium, emit no cue.
3. Earcon: OscillatorNode -> GainNode -> StereoPannerNode -> destination.
   - critical: three ~880 Hz beeps; high: two ~660 Hz beeps; medium: one ~440 Hz beep.
   - each beep 70–110 ms with a short attack/release on the gain (avoid clicks).
   - pan: alert-sourced cue -> 0 (ahead); detection-sourced cue -> by side (left -0.7, center 0,
     right +0.7), or cx/480*2 - 1.
4. Vibration: navigator.vibrate (guard for absence) — critical [120,60,120,60,120],
   high [100,50,100], medium [80].
5. De-dup: store the last cue signature (`${source}:${rank}`) and timestamp; fire only on change,
   on escalation, or after the condition cleared and returned; enforce a ~1500 ms min re-fire gap.
6. Gate cues exactly like speech: skip when isSpeechMuted() or qaInProgressRef/qaModeRef are active.
   Add a "Cues" on/off toggle (default on) in the P1 settings area.

CONSTRAINTS
- Frontend only. Do not delay or alter the existing speak(data.speech) call — cues run alongside it.
- No new dependencies (use Web Audio + the Vibration API directly).

VERIFY
- grep shows AudioContext, createOscillator, StereoPanner|panner, and navigator.vibrate in src/.
- With the backend running, bring a hazard into view (or temporarily hardcode a fake critical alert
  in the response handler): a critical earcon triple-beeps and (on a phone) vibrates; a left-side
  object pans left.
- Mute → no cue and no speech. Ask a voice question → cues suppressed during Q&A.
- A static safe scene does NOT beep every 2.5 s (de-dup works).

NOTE: test vibration on a real Android/Chrome device; desktop browsers usually no-op vibrate.
```

---

## PROMPT 3 — Clock-face directions + step distances, PRIORITY MODE ONLY (§3.4)

*Backend only. The naive baseline and all shared hazard wording must stay byte-for-byte identical.*

```text
GOAL
In priority mode, narrate objects with orientation-and-mobility wording: clock-face directions
("at 11 o'clock") and step counts ("about three steps") instead of left/center/right + metres.
The naive branch and hazard narrators must NOT change (they anchor the naive-vs-priority study).

FILES
- backend/engine/narrate.py   (add helpers + a flag to narrate())
- backend/server.py           (pass the flag in the PRIORITY branch only)

CONTEXT
- server.py has two object-speech branches:
    NAIVE (leave untouched): ". ".join(f"{d['class']} on your {d['side']}, {d['distance_str']} away"
                             for d in detections)
    PRIORITY: object_speech = eng_narrate.narrate(changed)
- Detections carry: class, side, cx (px center-x), distance (float metres), distance_str, motion,
  urgency_band, track_id. Frame width in the periodic loop is 480 (also `w` in server.py).
- narrate.py has: narrate(dets), _single_phrase, _group_phrase, _apply_urgency ("Stop."/"Warning.").

IMPLEMENT (narrate.py)
1. Add helpers:
   - _clock_direction(cx, frame_w): x = (cx/frame_w)*2 - 1  (in [-1,1]); offset = round(x * SPREAD)
     with SPREAD=2 as a named, tunable constant; hour from offset clamped to {10,11,12,1,2}
     (-2->10, -1->11, 0->12, +1->1, +2->2). Return e.g. "11 o'clock".
   - _steps_from_metres(m, step_len=0.75): if m < step_len return "right in front of you";
     n = max(1, round(m/step_len)); return "one step" if n==1 else f"about {n} steps".
2. Change signature to narrate(dets, frame_w=None, use_clockface=False). When use_clockface is True
   AND frame_w is set, phrases use _clock_direction(cx, frame_w) in place of "on your {side}" and
   _steps_from_metres(distance) in place of the metre distance. Keep the existing grouping rule
   (group same-class only when none moving); for a group use the nearest member's clock + steps.
   Keep _apply_urgency prefixes. When use_clockface is False, output is identical to today.

IMPLEMENT (server.py)
3. In the PRIORITY branch only: eng_narrate.narrate(changed, frame_w=w, use_clockface=True).
   Do NOT touch the naive inline string. Do NOT change narrate_dropoff/overhead/staircase/path —
   they are shared by both modes and must remain in metres/"ahead".

CONSTRAINTS
- Pure string logic; no new imports or models; deterministic.
- The naive branch and every hazard narrator must be unchanged (confirm via git diff).

VERIFY
- cd backend && python -c "from engine import narrate; print(narrate.narrate([{'class':'chair','side':'left','cx':96,'distance':2.3,'distance_str':'2.3 m','motion':'still','urgency_band':'low','track_id':1}], frame_w=480, use_clockface=True))"
  → prints roughly:  chair at 11 o'clock, about three steps.
- The same call with use_clockface omitted prints the original "on your left … 2.3 m" style.
- git diff shows the naive branch line and all hazard narrators untouched.
- Live: priority mode says "at N o'clock / about N steps"; switching to naive returns to
  "on your left, 2.3 m away".
```

---

## PROMPT 4 — Fix `Demo.jsx`, add the `/dashboard/chat` route, fix `.env.example`

*Frontend only. Three small, independent repairs.*

```text
GOAL
Repair three defects from the audit: Demo.jsx posts to an undefined base URL; a link points to a
missing /dashboard/chat route; .env.example uses the wrong (CRA) env var name.

FILES
- src/pages/Demo.jsx
- src/App.jsx           (routes)
- .env.example          (repo root)
- whatever component links to /dashboard/chat (grep for it)

CONTEXT
- Demo.jsx fetches `${apiUrl}/analyze_frame` but apiUrl is an undefined prop -> "undefined/analyze_frame".
  VisionPage.jsx does it right: const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000'.
- A link/nav item targets /dashboard/chat but no <Route> exists for it.
- .env.example declares REACT_APP_API_URL, but this is a Vite app that reads VITE_API_URL.

IMPLEMENT
1. Demo.jsx: replace the undefined apiUrl with the same env-based base URL VisionPage uses, and fetch
   against it. If Demo is a stale duplicate of VisionPage and nothing links to it (grep first), delete
   the file and remove its route/imports instead.
2. App.jsx: add a working <Route path="/dashboard/chat"> pointing at the intended existing component,
   OR remove the dead link if chat is not a real page. Do not scaffold a brand-new feature — match
   what already exists.
3. .env.example: replace REACT_APP_API_URL with `VITE_API_URL=http://localhost:5000` and add a
   one-line comment.

CONSTRAINTS
- Surgical fixes only. Confirm each delete/route decision against what actually exists before acting.

VERIFY
- grep: no remaining "undefined/analyze_frame" risk (Demo uses the env base URL, or Demo is gone with
  no dangling imports/routes).
- Visiting /dashboard/chat resolves (no blank screen / router warning), or the link is removed.
- grep: no REACT_APP_ left in .env.example; VITE_API_URL present.
- npm run build succeeds.
```

---

## PROMPT 5 — Deterministic replay `dt` + scope the indoor depth model (§eval validity)

*Backend + eval harness. Live behaviour must be unchanged when the new field is absent.*

```text
GOAL
Make offline-evaluation TTC/velocity independent of machine speed by driving motion dt from video
time (not wall clock), and explicitly document the depth model as indoor-calibrated.

FILES
- backend/engine/motion.py    (accept an injected timestamp)
- backend/server.py           (read frame_ts, pass it to update_motion inside simple_detection_facts)
- backend/replay_eval.py       (send frame_ts = video-time seconds)
- backend/engine/depth.py      (scope note)

CONTEXT
- motion.py update_motion(detections, frame_w) sets now = time.monotonic() and dt = max(now - t0, 1e-3).
  On replay, dt is the wall-clock gap between POSTs; replay_eval already sleeps to pace ~interval apart,
  but processing jitter still leaks into dt, so TTC varies run to run.
- replay_eval.py knows the true timeline: fps = cap.get(cv2.CAP_PROP_FPS); it samples every `stride`
  frames and increments a `sent` counter per posted frame. Video-time per posted frame = sent * interval
  (equivalently frame_idx / fps).
- depth.py uses Depth Anything V2 Metric Indoor Small — metres are reliable indoors, not outdoors.

IMPLEMENT
1. motion.py: add optional param now_ts=None to update_motion; set now = now_ts if now_ts is not None
   else time.monotonic(). Nothing else changes.
2. server.py: in /analyze_frame read optional form field `frame_ts` (float seconds, None if absent).
   Locate the update_motion(...) call inside simple_detection_facts and pass now_ts=frame_ts.
   Live requests omit frame_ts -> monotonic path, unchanged.
3. replay_eval.py: add 'frame_ts' to the POSTed data dict = the frame's video-time in seconds
   (sent * interval, or frame_idx / fps). Keep the real-time pacing sleep.
4. depth.py: add a short docstring/comment stating the model is metric-indoor-calibrated and outdoor
   distance/TTC/drop-off are qualitative. (Only if trivial: read an optional env VE_DEPTH_SCALE at load
   to rescale for outdoor clips; otherwise just document.)

CONSTRAINTS
- Live path untouched when frame_ts is absent. No new dependencies. Change only the timestamp seam —
  do not refactor motion classification.

VERIFY
- cd backend && python -c "from engine import motion; motion.reset_motion(); d=[{'track_id':1,'distance':5.0,'cx':240}]; motion.update_motion(d,480,now_ts=0.0); d=[{'track_id':1,'distance':4.0,'cx':240}]; motion.update_motion(d,480,now_ts=1.0); print(round(d[0]['closing_speed_mps'],2), round(d[0]['ttc'],2))"
  → 1.0 4.0  (regardless of machine speed).
- Replay the same clip twice with different --interval real pacing but the same sampling → the TTC
  columns in study_logs match.
- A live camera run still works (no frame_ts sent).
```

---

## PROMPT 6 — Housekeeping: remove dead code, refresh docs, add ARIA

*Mixed backend + frontend. Do this last. Every removal must be preceded by a grep proving it's unused.*

```text
GOAL
Remove confirmed dead code, correct stale comments/docs, and add basic screen-reader support to the
vision view.

FILES
- backend/server.py
- backend/engine/__init__.py
- src/pages/VisionPage.jsx

CONTEXT (all confirmed in CODEBASE_AUDIT.md)
- server.py scan_terrain_hazards(depth_map) (~L223) is never called; /analyze_frame detects hazards
  inline. Calling it in addition would double-increment dropoff/staircase confirmation streaks.
- server.py /query endpoint (~L842) is never called by the frontend (it uses /question and /ocr).
- server.py hazard-policy comments (~L693 and ~L726) say only "drop-off (critical) > overhead (high)"
  and omit staircase, which is actually in the ordering.
- engine/__init__.py module docstring lists 9 modules and omits dialogue.py.
- VisionPage.jsx has no ARIA and reads data.caption and data.wall_alert, which the backend never sends.

IMPLEMENT
1. Delete scan_terrain_hazards after grepping to confirm zero call sites.
2. Remove the /query route after grepping the frontend for '/query' to confirm no caller. Keep helpers
   it shared (describe_scene, locate_target, read_text) — /question and /ocr use them; remove only the
   dead route.
3. Fix the two server.py comments to the real order:
   drop-off (critical) > staircase (high) > overhead (high) > path/objects.
4. Add dialogue to the engine/__init__.py module list, e.g.
   "dialogue  - conversational NLU + short-lived session memory for voice Q&A".
5. VisionPage.jsx: add a visually-hidden aria-live="assertive" region mirroring the latest spoken text;
   add aria-labels to Start/Stop/mode/agility/cues controls; give the vision view a sensible role/label.
   Remove the dead data.wall_alert branch (and data.caption unless it feeds a visible debug element).

CONSTRAINTS
- Precede each removal with a grep proving it's unused. Do not change live hazard-pipeline behaviour.
- ARIA changes must not alter the visual layout.

VERIFY
- grep: no definition/call of scan_terrain_hazards; no '/query' route and no frontend caller.
- cd backend && python -c "import ast; ast.parse(open('server.py').read())" (syntax OK); server boots:
  python server.py.
- engine/__init__.py docstring now names dialogue.
- grep: aria-live present in src/pages/VisionPage.jsx; no data.wall_alert handler remains.
- npm run build succeeds.
```

---

## After all six

Run a full end-to-end smoke test with both servers up:

1. Start the vision loop → switch **Cautious** → confirm the network request carries `agility=low` and warnings come earlier.
2. Bring a hazard into view → hear speech **and** a panned earcon; feel vibration on a phone.
3. In **priority** mode confirm "at N o'clock / about N steps"; flip to **naive** and confirm the original "on your left, 2.3 m away".
4. `python replay_eval.py <clip> --mode priority` then `--mode naive`, then `python analyze_study.py study_logs/*.jsonl` → TTC numbers are stable across runs.
5. `npm run build` and a backend boot both succeed.

Commit after each prompt; if any VERIFY step fails, fix it before advancing rather than stacking changes.

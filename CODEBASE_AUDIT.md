# Virtual Eye 3.0 — Codebase Audit Against the Blind-Centered Plan

**Audited:** 2026-08-16
**Plan of record:** `backend/refer.md` ("Making Virtual Eye Genuinely Blind-Centered" — Tier 1/2/3 upgrade list + integration sketch)
**Scope:** every backend engine module + `server.py`, and the full frontend (`src/`), checked feature-by-feature against the plan.

> Verdict key: ✅ conforms / implemented and wired · ⚠️ partial — implemented but not fully reachable or has a caveat · ❌ missing or broken.
>
> Note: per the current working agreement, this audit does **not** re-open the deferred grey-stairs recognition discussion. Where `detect_staircase` and the vehicle-geometry veto appear, they are documented factually as code that now exists, without a fix write-up.

---

## 1. Executive summary

The backend has moved a long way toward the plan and, in several places, **past** it. All three Tier-1 safety features are implemented and correctly wired: head-height hazards (3.1), descending drop-offs (3.2, with the earlier inverted-sign bug fixed), and TTC urgency bands with agility, vehicle weighting and debounce (3.3). The plan's ISANA-style "actionable-only" gating (3.6) is implemented, and there is now a substantial conversational Q&A layer (`dialogue.py` + `/question`) that satisfies and exceeds the plan's scene-description ambition (3.8). Two features beyond the plan — **staircase detection** and a **vehicle-class geometric veto** — are also present. Session/state hygiene (`/reset`) and study telemetry are solid.

The gap is almost entirely at the **frontend boundary**. The backend already emits everything Tier-2 needs (per-object `urgency`, a structured `alerts[]` list, hazard distances and confidences), but the frontend consumes only the `speech` string. As a direct result:

- **Personalization (3.3/3.7) is unreachable.** The backend reads an `agility` form field, but the frontend never sends it — every user is treated as "high" agility.
- **Non-speech cues (3.5) are absent.** No earcons, no stereo-panned/spatial audio, no `navigator.vibrate`.
- **Clock-face directions and step distances (3.4) are absent** — narration still uses left/center/right thirds and metres.

None of these require new models or hardware; they are frontend work on top of a backend contract that already exists. That makes them the highest-leverage items on the list.

---

## 2. Plan conformance matrix

| Plan feature | Status | Where / evidence |
|---|---|---|
| 3.1 Head-height / overhead hazard | ✅ | `path.analyze_overhead` → `narrate.narrate_overhead`; wired `server.py` L641, alert L708, spoken L746 |
| 3.2 Drop-off / descending step | ✅ | `path.detect_dropoff` (sign-correct `far−near>0`, gradient-gated, 2-frame confirm); spoken **first** `server.py` L645/699/736 |
| 3.3 TTC urgency bands + agility + vehicle weight + debounce | ⚠️ | Fully implemented in `priority.py` and voiced in `narrate.py`; **agility never sent by the UI** → always defaults "high" |
| 3.4 Clock-face directions + step distances | ❌ | Not implemented; `narrate`/`choose_side` still use L/C/R thirds + metres |
| 3.5 Earcons / spatial audio / vibration | ❌ | No Web Audio, no panning, no `vibrate` anywhere in `src/`; backend emits `urgency`+`alerts[]` that would drive it |
| 3.6 Actionable-only gating (ISANA) | ✅ | `priority.is_actionable_risk` + `prioritize(actionable_only=True)` |
| 3.7 Settings / personalization panel | ❌ | No settings UI; agility/units/verbosity/directions/modality prefs not surfaced (backend supports `agility` only) |
| 3.8 Landmark / scene description + conversational Q&A | ✅ | `dialogue.py` + `/question` (describe/find/distance/side/reach/surface/nearby/count), Florence-2 caption + dense regions, session memory — beyond plan |
| 3.9 Street-crossing assist | ❌ | Not implemented (later tier) |
| 3.10 Wearable belt / haptics hardware | ❌ | Out of software scope (later tier) |
| 3.11 Indoor wayfinding / mapping | ❌ | Not implemented (later tier) |
| Bonus — staircase detection + vehicle-geometry veto | ✅ | `path.detect_staircase`, `path.plausible_vehicle_geometry`, `narrate.narrate_staircase` |
| State hygiene / reset | ✅ | `/reset` → `reset_all_engine_state` clears motion, TTC debounce, path streaks, dialogue memory, ByteTrack |
| Naive-vs-priority study telemetry | ✅ | `telemetry.py` + expanded `log_frame` (agility, alerts, per-det TTC/urgency, path) |

---

## 3. Backend engine — per-file audit

### `engine/__init__.py` — ✅ (minor drift)
Package docstring / module roadmap. Accurate for the original nine modules. **Minor:** the list does not mention `dialogue.py` (added later). Documentation-only.

### `engine/depth.py` — ✅ (validity caveat)
Depth Anything V2 **Metric Indoor Small**. `compute_depth_map` (bicubic resize to frame size), `object_distance_from_depth` (median over central 40 % of the box, clamped 0.2–20 m), `format_distance`. Clean and correct.
**⚠️ Validity caveat:** it is an *indoor* metric model, yet several plan scenarios are outdoor (curb drop-offs, vehicle TTC, street-crossing 3.9). Outdoors the metric scale can be unreliable, which propagates into distance, TTC, drop-off and overhead. Validate on real outdoor clips, or document the system as indoor-scoped.

### `engine/motion.py` — ✅ (evaluation caveat)
ByteTrack-history motion state (approaching / crossing / moving away / still), signed depth velocity, closing speed, and TTC computed only while approaching. Thresholds and stale-track GC are sensible.
**⚠️ Evaluation caveat:** `dt` comes from `time.monotonic()` (wall-clock). On `replay_eval` over recorded video, velocity/TTC therefore reflect *processing rate*, not the video's real timeline — TTC magnitudes will vary with machine speed. For fair naive-vs-priority TTC numbers, drive `dt` from frame index × known FPS during replay.

### `engine/color.py` — ✅
HSV sampling (torso region for `person`, central patch otherwise); achromatic pixels resolve to black/white/gray by brightness. Reasonable and dependency-light. (Grey surfaces legitimately return "gray"; this is expected behavior of the colour namer.)

### `engine/priority.py` — ✅ (core contribution, matches plan)
- `urgency_band(ttc, agility)` — high-agility high<3 s/med<6 s; low-agility high<4 s/med<8 s; `ttc≤0`→critical. Matches plan §3.3.
- `dynamic_threat_weight` — vehicles +10, person +8, other dynamic +5 (only when approaching/crossing).
- `TTCDebouncer` — requires an N-frame *decreasing* TTC trend before confirming "high"; fires instantly on `ttc≤0`. Matches the plan's false-alarm suppression.
- `compute_priority_score` — transparent additive components (TTC band, dynamic threat, in-path, hazard class, motion); writes `urgency_band` onto the detection.
- `is_actionable_risk` — the plan's 3.6 actionable filter (approaching animate hazards with confirmed high/med urgency; near crossing; in-path vehicles/static/trip hazards within class-specific distances).
- `prioritize` — updates TTC state → scores → suppresses unconfirmed "high" by −15 → applies actionable filter → returns top-K. Correctly called **with `agility=`** from the server.
- `should_announce_now` / `should_announce_hazard_now` — state-change + reminder + semantic-dedup + escalation gating; hazard gate allows escalation to re-announce.
- `reset_priority_state` — clears debounce.

### `engine/path.py` — ✅ (comprehensive)
- `analyze_path` — corridor walkability → clear / left / right / stop with robust percentile depth.
- `should_announce_verdict` — path-state change gate.
- `analyze_overhead` (3.1) — top-35 % × central-50 % ROI, robust near-depth ≤1.5 m + coverage/near-fraction gates + confidence.
- `detect_dropoff` (3.2) — **sign-correct** (`jump = far − near`), ratio + gradient-multiple gate to beat perspective, near-edge anchoring, edge-replicated smoothing, 2-frame confirmation; reports the *edge* distance.
- `detect_staircase` — several evenly-spaced small risers (distinct from one big drop-off), spacing-CV periodicity test, 2-frame confirmation.
- `plausible_vehicle_geometry` — vetoes a vehicle-class box whose interior depth profile shows staircase-like stepping.
- `reset_path_state` — clears `_last`, `_dropoff_streak`, `_staircase_streak`.
**Minor:** corridor definitions differ across modules (path 0.30–0.70, priority in-path 0.33–0.66, overhead/dropoff central 0.50). Not a bug, but not unified.

### `engine/narrate.py` — ✅ (matches §3.3 voicing)
Urgency escalation is now audible: `_apply_urgency` prepends **"Stop."** (critical) / **"Warning."** (high); `_single_phrase` uses "less than one metre" wording; `narrate` groups same-class objects only when none are moving (so a moving threat keeps its motion + distance). Hazard narrators `narrate_path` / `narrate_overhead` / `narrate_dropoff` / `narrate_staircase` (color-aware) and the conversational builders `narrate_find` / `narrate_surface_contents` / `narrate_nearby` / `narrate_scene_description` / `narrate_read` are all present.

### `engine/vlm.py` — ✅ (VRAM caveat)
Florence-2-base: `describe_scene` (`<MORE_DETAILED_CAPTION>`), `find_object` (`<OPEN_VOCABULARY_DETECTION>`), `dense_region_captions` (`<DENSE_REGION_CAPTION>`), plus support-surface inference and a Windows `flash_attn` import shim.
**⚠️ VRAM caveat:** loaded at startup and kept warm alongside YOLOv8n and Depth-V2 on a 6 GB GPU. OCR being lazy mitigates this, but the three warm models are the tight budget — worth monitoring.

### `engine/dialogue.py` — ✅ (beyond plan)
NLU for spoken scene questions: intent classification (locate / distance / side / reach / surface-contents / nearby / describe / count / region / summary), pronoun + follow-up resolution, thread-safe `DialogueMemoryStore` (15-min TTL), and geometric relational helpers (`bbox_supported_by`, `items_on_surface`, `nearest_scene_item`). Robust foundation for the voice-first experience.

### `engine/ocr.py` — ✅
Lazy EasyOCR (en/hi/mr); `read_text` with confidence filter. Never touches the periodic loop, keeping startup VRAM low — matches the plan's "read this" intent.

### `engine/telemetry.py` — ✅
Thread-safe JSONL, `start_session` / `log_frame` / `stop_session`. Frame-oriented schema well suited to the naive-vs-priority study and offline latency/false-alert analysis.

---

## 4. Backend orchestrator — `server.py`

**Endpoints:** `/health`, `/analyze_frame` (periodic loop), `/query` (describe|find|read), `/question` (session-aware voice Q&A), `/telemetry/stop`, `/calibrate` + `/get_calib_K` + `/reset_calib` (legacy), `/ocr` + `/ocr_url` + `/ocr_pdf`, `/reset`.

**✅ Wiring is correct and matches the plan's integration sketch:**
- One depth map per frame, reused by path/overhead/dropoff/staircase (no redundant model calls).
- `agility` threaded into `prioritize(...)`.
- Hazard-first spoken policy: drop-off (critical) → staircase → overhead → path/objects; only the single highest structural event is spoken, while the full `alerts[]` is still returned.
- Vehicle-geometry veto applied inside the detection loop before distance/color.
- `/reset` → `reset_all_engine_state` clears motion history, TTC debounce, path streaks, `_last_announced`, dialogue memory, and ByteTrack trackers — closing the earlier "reset never wired" gap.
- Telemetry logs mode, agility, alerts, per-detection TTC/urgency/confirmation, path verdict, latency, words.

**⚠️ / ❌ findings:**
- **`agility` and `session_id` are read from the form but the frontend never sends them to `/analyze_frame`** → personalization is inert and the periodic loop's telemetry sessions get auto-generated names (see §5).
- **`/query` is dead** — the frontend calls `/question` and `/ocr` instead, never `/query`. Harmless but confusing; either wire or remove.
- **`scan_terrain_hazards` (L223) is defined but never called** — it duplicates the inline detector logic in `/analyze_frame`. Risk: if it is ever called *in addition* to the inline calls, it double-increments the drop-off/staircase confirmation streaks.
- **`lang` form field is documented but never read** (reserved for localization).
- **Stale comments** at L693 / L726 describe only "drop-off (critical) > overhead (high)" and omit staircase, which was added later.
- Florence-2 load is wrapped in try/except (degrades `/query` describe|find on failure); note the `/question` "describe" path depends on the same model.

---

## 5. Frontend — per-file audit (`src/`)

> The frontend lives at the **repo root `src/`** (not `frontend/src/`). `VisionPage.jsx` correctly reads `import.meta.env.VITE_API_URL` (default `http://localhost:5000`).

| File | Role | Verdict |
|---|---|---|
| `main.jsx`, `App.jsx` | App shell + routing | ✅ |
| `context/ModeContext.jsx` | Priority/Naive toggle (default priority) + `voice-set-mode` | ✅ drives the study modes |
| `context/VoiceNavigationContext.jsx` | `SpeechRecognition` + hardened `speechSynthesis` with mic coordination | ✅ core voice I/O |
| `pages/VisionPage.jsx` | Main loop: capture 480×360 JPEG → `POST /analyze_frame` (mode) → speak `speech`; `/question` for voice Q&A (sends `session_id`); `/reset` on start/stop | ⚠️ see gaps below |
| `pages/OCRPage.jsx` | Smart Reader (`/ocr`, `/ocr_url`, `/ocr_pdf`) | ✅ |
| `pages/Demo.jsx` | Demo capture page | ❌ **broken** — posts to `` `${apiUrl}/analyze_frame` `` where `apiUrl` is undefined → `undefined/analyze_frame` |
| `pages/DashboardHome.jsx`, `LandingPage.jsx`, `components/layout/DashboardLayout.jsx` | Marketing / dashboard shell (hosts Priority/Naive toggle) | ✅ (see route gap) |

**Verified frontend integration gaps (checked directly, not just reported):**
- **`agility` appears nowhere in `src/`** → 3.3/3.7 personalization cannot be exercised from the UI.
- **`session_id` is sent to `/question` (L206, L583) and `/reset` (L280, L362) but not to `/analyze_frame` (L422)** → periodic-loop telemetry is not tied to the voice session id.
- **No `vibrate`, `AudioContext`, `createOscillator`, `StereoPanner`, or earcon logic** → Tier-2 non-speech cues (3.5) entirely absent.
- **The frontend consumes only `speech`.** The structured `alerts[]`, `urgency`, `dropoff`, `overhead`, and `staircase` fields the backend returns are ignored (the only match is a comment at `VisionPage.jsx:469`). This is the single biggest piece of already-built backend value going unused.
- Reported by earlier sweep and consistent with the above: `help`↔`SOS` keyword overlap in the voice branch, a linked-but-missing `/dashboard/chat` route, and no ARIA on the core vision view.
- `.env.example` uses `REACT_APP_API_URL` (Create-React-App style) while the code is Vite (`VITE_API_URL`) — stale example; the `localhost:5000` default masks it in practice.

---

## 6. Cross-cutting findings & validity risks

1. **Indoor metric depth used for outdoor scenarios** — affects distance/TTC/drop-off/overhead validity outdoors (see `depth.py`). Validate on outdoor clips or scope the claims to indoor.
2. **Wall-clock `dt` on replay** — TTC/velocity on `replay_eval` reflect processing speed, not the video timeline; anchor `dt` to FPS for defensible study numbers.
3. **Warm-model VRAM budget** — YOLOv8n + Depth-V2-Small + Florence-2-base co-resident on 6 GB; lazy OCR helps.
4. **Speech-only frontend** — the backend's Tier-2 structured contract (urgency, alerts, hazard distances) is fully populated but unused; wiring it unlocks 3.4/3.5/3.7 with no backend change.
5. **Dead / drifted code** — `/query` endpoint, `scan_terrain_hazards`, the `lang` field, stale hazard-policy comments, and `__init__` omitting `dialogue.py`.
6. **Corridor constants not unified** across path/priority/overhead/dropoff.

---

## 7. Prioritized gap list

**P1 — Make personalization reachable (3.7 → unlocks 3.3).** Add a settings control and send `agility` (and `session_id`) with the `/analyze_frame` request. Highest value, lowest effort: the backend already honours both.

**P2 — Consume `alerts[]` / `urgency` in the UI (3.5).** Map urgency/priority to earcons + stereo-pan + `navigator.vibrate`. All required data is already in the response.

**P3 — Clock-face directions + step distances (3.4).** Localized change in `narrate.py` (and the side computation) toward O&M-native wording ("obstacle at 11 o'clock", "about three steps").

**P4 — Fix or remove `Demo.jsx`** (undefined `apiUrl`); add the missing `/dashboard/chat` route; align `.env.example` to `VITE_API_URL`.

**P5 — Protect evaluation validity.** Drive `replay_eval` `dt` from video FPS; validate (or scope) the indoor depth model for outdoor clips.

**P6 — Housekeeping.** Remove or wire `scan_terrain_hazards` and `/query`; refresh stale comments and the `__init__` module list; add ARIA to `VisionPage`.

**Deferred (later tiers):** 3.9 street-crossing, 3.10 wearable belt, 3.11 indoor wayfinding.

---

## 8. Bottom line

Tier-1 safety (3.1, 3.2, 3.3) and the plan's actionable-gating (3.6) and scene Q&A (3.8) are implemented and correctly wired, plus two bonus detectors. The remaining plan items (3.4, 3.5, 3.7) are blocked almost entirely at the frontend, which today speaks the backend's `speech` string but ignores the richer structured output built for exactly those features. Closing P1–P3 would bring the running app up to the full Tier-1 + early-Tier-2 experience described in `refer.md` without any new model or hardware.

# Making Virtual Eye Genuinely Blind-Centered
### A research-grounded plan to strengthen the priority & decision layer

*Prepared for Ayush · Virtual Eye 3.0 · 2026-08-11*
*Sources are top-venue: ACM ASSETS / TACCESS / Proc. ACM HCI, IEEE, Scientific Reports, the O&M practitioner literature, and WHO. Full citation list at the end.*

---

## 0. How to read this document

You already built the hard part: a working perception stack (YOLOv8n + ByteTrack, Depth Anything V2, Florence-2, EasyOCR) with a priority/decision engine and a naive-vs-priority telemetry study. This document does **not** ask you to rebuild anything. It shows what the leading research says blind travellers actually need, and turns that into a **ranked list of upgrades to your decision layer** — every one of which is implementable on your current laptop (RTX 3050 6 GB), in the browser, with **no new hardware and no new heavy models**. Most are refinements to `priority.py`, `path.py`, `narrate.py`, and the frontend audio.

The single most important finding, which reframes your whole contribution, is in Section 2.1.

---

## 1. Who the users actually are (and why it shapes the design)

**Scale.** The WHO (2023) estimates **2.2 billion** people live with vision impairment; the Global Burden of Disease Study (2020) counts **43.3 million blind** and **295 million** with moderate-to-severe vision impairment. Most are **over 50**, which matters: an older user has slower reaction time and lower "agility" — a parameter we will use directly when tuning alert timing.

**Consequences your project targets.** Vision impairment is associated with a **higher risk of falls and fractures**, social isolation, and lower employment (WHO). "Falls" is not a soft outcome — it is one of the two hazards the standard mobility aid physically cannot cover (Section 2.2).

**The mobility framing (O&M).** Rehabilitation professionals split the problem into **Orientation** (knowing where you are, using landmarks and spatial relationships) and **Mobility** (moving safely — obstacle avoidance, tripping hazards, drop-offs, apertures, straight-line travel). Instructors teach a four-step loop: **notice → interpret → act → anticipate** sensory cues. Your system should map onto this vocabulary, not invent its own. Two concrete conventions blind travellers are *trained* on — **clock-face directions** and **step-counted distances** — are things your narration currently doesn't use, and adopting them is nearly free (Section 3.4).

> **Design takeaway.** Your users are not "sighted people with the screen off." They come with a trained mental model (landmarks, clock directions, cane technique) and, often, age-related slowness. The system earns trust by speaking their language and by covering exactly the gaps their cane leaves.

---

## 2. The three findings that should reshape your priority layer

### 2.1 Cognitive load — not detection — is the real bottleneck

This is the most important result in the field for your project. Skovfoged, Rasmussen, Kirsh & Knoche, *"The Cost of Knowing: How Obstacle Alerts Reduce Walking Speeds of Augmented White Cane Users"* (**Proc. ACM HCI, 2022**), ran controlled within-subject studies (6 visually impaired + 10 blindfolded) comparing a plain white cane to augmented canes with different preview types and ranges. The finding:

> The slowdown augmented canes cause is driven by the **cognitive cost of processing extra, unnecessary, or complex alerts** — *not* by the physical act of detecting obstacles. Those extra alerts "neither helped reduce collisions nor [helped] physically detect obstacles," and "should be kept to a minimum."

Independently, the ISANA indoor navigation aid and multiple surveys reach the same conclusion: cognitive load is *the* leading barrier to real-world adoption of electronic travel aids, and adoption rates remain very low despite decades of better sensors.

**Why this matters to you:** it is the academic justification for your entire priority engine. Your naive-vs-priority study is measuring *exactly* the variable the literature says matters most (words spoken / announcements = cognitive load proxy). Frame your contribution as **"a cognitive-load-aware decision layer,"** cite this paper, and your "quieter but not less safe" result becomes a direct empirical contribution to an open problem — not just an engineering nicety.

### 2.2 The two hazards the cane cannot cover — and your camera can

The white cane is dominant because it is cheap, robust and reliable, but the O&M literature is unanimous about its two blind spots:

1. **Head- and upper-body-level obstacles** (tree branches, propped-open windows, shelves, signs, truck mirrors). The cane surveys the ground and its own length; it gives **zero** protection above the waist. In a survey of ~300 BVI people, **13% reported head-level accidents at least monthly**, and the aid type (cane or dog) made no difference.
2. **Drop-offs / descending stairs / curbs.** Uncertain discrimination of drop-offs is a known cane weakness and a direct fall risk.

**A chest- or head-height camera is the natural instrument for both.** This is the strongest "why a camera, not just a cane" argument you can put in your report — and both detections are computable from the **depth map you already produce**, with pure NumPy (Section 3.1–3.2). This is where you differentiate from every ultrasonic smart-cane project.

### 2.3 Semantic priority: not all obstacles are equal, and timing must be personalized

Two complementary results:

- **Actionable vs non-actionable filtering (ISANA).** Only obstacles that block the path or move toward the user trigger a re-route/alert; obstacles off the path get at most a low-key mention. Your `path.py` already computes a corridor — you can gate object announcements by "is it in my corridor?" almost for free (Section 3.3).
- **TTC urgency bands, personalized by agility.** A walking-information provision system maps time-to-collision to discrete urgency levels and *adapts them to the user*: a high-agility user gets **low = 10–6 s, medium = 6–3 s, high = <3 s**; a low-agility user gets **no "low" band at all** (medium = 10–5 s, high = <5 s) so warnings come earlier. Automotive systems add a **~2 s** hard warning threshold plus a **consecutive-decrease counter (~5 frames)** so a single noisy depth reading can't fire a false alarm. You already compute `ttc` in `motion.py`; adopting these exact bands turns it into a defensible, cited design (Section 3.3).

---

## 3. The upgrade list — ranked, evidence-linked, feasibility-rated

Each item notes the **blind-specific rationale**, the **file(s) to touch**, **effort**, and **GPU/hardware cost** (all are ≈0 unless noted). Ordered by *value ÷ effort*.

### Tier 1 — High value, low effort (do these for the 40-day review)

**3.1 Head-height / upper-body hazard alert** ⭐ *the flagship gap-filler*
- **Rationale:** covers the cane's #1 uncovered hazard (13% monthly head accidents). No smart-cane can do this; your camera can.
- **How:** take the **upper region of the depth map** (say top 35% of frame, central corridor width) and if the nearest robust depth there is < ~1.5 m, emit a distinct high-priority alert: *"Head height obstacle ahead."* Reuse `path.py`'s robust-percentile logic; add an upper-ROI pass.
- **Files:** new `analyze_overhead()` in `path.py`; wire into `/analyze_frame`; new phrase in `narrate.py`.
- **Effort:** ~half a day. **GPU:** none (reuses existing depth map).

**3.2 Drop-off / descending-stair / curb warning** ⭐
- **Rationale:** the cane's #2 gap; direct fall-prevention. Depth-based descending-stair detection hits >94% danger-vs-safe in the literature (EURASIP JIVP 2016) on far weaker hardware.
- **How:** in the **lower-central ROI**, the floor's depth should increase smoothly with distance. A **sudden jump** (discontinuity) or a region reading much farther than the expected floor plane indicates a downward drop / descending step. Flag *"Caution, step down ahead"* / *"Drop off ahead, stop."*
- **Files:** new `detect_dropoff()` in `path.py`; phrase in `narrate.py`.
- **Effort:** ~1–1.5 days (needs threshold tuning against your recorded clips). **GPU:** none.
- **Note:** be conservative — false negatives are dangerous, false positives erode trust. Tune for high recall on your stair/curb clips, and always pair with "stop."

**3.3 TTC urgency bands + moving-threat priority + debounce** ⭐ *core-contribution upgrade*
- **Rationale:** directly implements the cited urgency-mapping and false-alarm-suppression research; makes "a closing person/vehicle outranks a nearer static chair" principled rather than ad-hoc.
- **How, three parts:**
  1. **Bands:** replace the raw `urgency = max(0, 10 - ttc)` with the literature bands (low 10–6 s / med 6–3 s / high <3 s), and expose an **agility setting** (`high`/`low`) that shifts the bands earlier for low-agility users (drops the "low" band).
  2. **Vehicle weighting:** YOLO already labels `car`, `bus`, `truck`, `motorcycle`, `bicycle`, `person`. Give moving vehicles the top priority weight — a moving vehicle is the highest-stakes dynamic threat and the one blind pedestrians most fear (surveys around crosswalks).
  3. **Debounce:** require TTC to decrease for **N consecutive frames (≈3–5)** before firing the "high" alert, so one bad depth frame can't cause a false alarm.
- **Files:** `priority.py` (`compute_priority_score`, add `urgency_band()`), `motion.py` (already has `ttc`), a small `_ttc_history` for debounce; settings plumbed from frontend.
- **Effort:** ~1 day. **GPU:** none.

**3.4 Speak the blind vocabulary: clock-face directions + step distances** ⭐
- **Rationale:** blind travellers are *trained* on "obstacle at 11 o'clock" and step counts; O&M explicitly teaches "turn to 11 o'clock" because "go that way" is meaningless without sight. Left/center/right (your current thirds) is coarser and non-native.
- **How:** add `choose_clock(cx, frame_w)` mapping horizontal position to 10–11–12–1–2 o'clock (you don't need a full 12 positions for a ~60° FOV — 5 buckets is realistic and honest). Convert metres → steps (~0.75 m/step) as an *option*. Narration becomes *"Person, 12 o'clock, 3 steps"* or, in metres for a low-vision user who prefers it, *"Person ahead, 2 metres."* Make it a user setting (clock vs left/right; steps vs metres).
- **Files:** `narrate.py` (+ a `choose_clock` helper next to `choose_side`); a settings toggle.
- **Effort:** ~half a day. **GPU:** none.

**3.5 Modality-by-urgency: earcons & spatial (stereo-panned) audio in the browser**
- **Rationale:** non-speech cues (earcons, auditory icons, and **spearcons** = time-compressed speech) convey information **faster and at lower cognitive load** than full sentences (Walker et al.; SIGACCESS meta-analyses). For an *imminent* hazard you don't want to wait for "There is a person approaching on your left" — a rising **looming tone** panned to the correct ear says "danger, that side, now" in ~300 ms.
- **How (frontend, Web Audio API / Tone.js — no GPU, no backend change):**
  - **High-urgency** (TTC "high", drop-off, head-height): short rising/looming earcon, **stereo-panned** to the object's side (left/right by `cx`), optionally pitch ↑ as distance ↓.
  - **Medium:** a brief earcon **then** a short spoken phrase.
  - **Low/descriptive:** speech as today.
  - Your backend already returns everything needed (`speech`, `path`, per-object `side`/`distance`); add an `urgency` field per announcement so the client can pick the cue.
- **Files:** frontend audio module; add `urgency` to the `/analyze_frame` JSON in `server.py`.
- **Effort:** ~1.5–2 days (mostly frontend). **GPU:** none.
- **Bonus, mobile:** trigger `navigator.vibrate([...])` patterns for high-urgency alerts when running on a phone — a cheap second modality, exactly the multimodal approach the belt/vibrotactile literature endorses (hands-free, low cognitive load).

### Tier 2 — High value, moderate effort (strong "future work," or stretch goals)

**3.6 Actionable-only object gating.** Using `path.py`'s corridor, suppress speech for objects clearly outside your walking path unless queried; announce in-corridor objects. Implements ISANA's actionable/non-actionable split → further cuts words spoken. *Files:* `priority.py` + `/analyze_frame`. *Effort:* ~half a day. This will *improve your study numbers* (fewer, more relevant announcements).

**3.7 Verbosity / personalization profile.** A small settings object: `agility` (fast/slow → TTC bands), `directions` (clock/left-right), `units` (steps/metres), `verbosity` (quiet/normal/chatty → top_k & min_score), `modality` (speech-only / speech+earcon / +vibration). Surveys consistently show blind users want **human-in-the-loop, query-based, adjustable** systems, not one-size-fits-all. *Files:* frontend settings panel + pass-through form fields; `server.py` reads them. *Effort:* ~1 day.

**3.8 Landmark-anchored "describe" for orientation.** Extend the `/query describe` intent to prefer **permanent landmarks** ("door on your right, corridor ahead") over transient clutter, matching how O&M uses landmarks to re-orient. Florence-2 already gives scene captions; add a light prompt/post-filter toward doorways, stairs, signage, corridors. *Files:* `vlm.py` prompt + `narrate.py`. *Effort:* ~1 day.

### Tier 3 — Genuine extensions (roadmap / next semester / publication)

**3.9 Street-crossing assistant.** The highest-stakes blind mobility task: a Minnesota study found **27% of unaided crossings ended with cross-traffic already moving**, and current apps read the *pedestrian signal*, not whether cars actually yield. Quiet EV/hybrids make audio-only judgment unreliable. A camera that detects **approaching vehicles + their motion** at a curb is a real contribution. Scope: vehicle detection you already have + a "curb/crossing mode." Big, but publishable. *Effort:* weeks. *GPU:* fits your stack.

**3.10 Wearable form factor + vibrotactile belt.** The natural hardware evolution: chest/waist camera + a simple vibrotactile belt (ALVU-style) encoding direction/distance/height. Belts give closer path-following than audio (Flores et al.) and free the ears. Out of scope for a browser demo, but the right "productization" slide. *Effort:* hardware project.

**3.11 Indoor wayfinding / narrative maps.** Turn-by-turn with clock directions and step counts ("proceed to 12 o'clock, 8 steps, door on your 3 o'clock") — the EOA/orientation half of O&M that pure obstacle-avoidance misses. *Effort:* large (needs mapping/localization).

---

## 4. What this looks like in your code (concrete integration sketch)

Everything below is an *addition* to existing modules — nothing is rewritten.

```
engine/path.py
  + analyze_overhead(depth_map, w, h)   -> {hazard: bool, dist: float}    # 3.1
  + detect_dropoff(depth_map, w, h)     -> {dropoff: bool, dist: float}   # 3.2

engine/priority.py
  ~ compute_priority_score(...)  # add vehicle-class weight               # 3.3
  + urgency_band(ttc, agility)   -> "low"|"medium"|"high"                 # 3.3
  + debounce_high(track_id, ttc) -> bool  (N-consecutive-decrease)        # 3.3
  + in_corridor(det, path_verdict) -> bool  # actionable gating           # 3.6

engine/narrate.py
  + choose_clock(cx, w)          -> "11 o'clock" ...                      # 3.4
  + fmt_distance(m, units)       -> "3 steps" | "2 metres"                # 3.4
  ~ narrate(...)                 # attach per-item `urgency`              # 3.5
  + narrate_overhead(), narrate_dropoff()                                 # 3.1/3.2

server.py  /analyze_frame
  + call analyze_overhead + detect_dropoff (reuse the depth_map you already have)
  + read settings: agility, directions, units, verbosity, modality       # 3.7
  + return `urgency` per announcement + top-level `alerts` list           # 3.5

frontend (VisionPage.jsx + new audio.js)
  + pick cue by urgency: earcon+pan (high) / earcon+speech (med) / speech (low)  # 3.5
  + navigator.vibrate patterns on mobile for high urgency                 # 3.5
  + Settings panel: agility / directions / units / verbosity / modality   # 3.7
```

> **One efficiency note you already flagged:** `/analyze_frame` currently calls `compute_depth_map` twice (once in `simple_detection_facts`, once for path). Since 3.1 and 3.2 also need the depth map, this is the moment to refactor `simple_detection_facts` to **return `(detections, depth_map)`** and pass that single map to path/overhead/dropoff. One change, pays for four features.

---

## 5. Evaluation upgrades (so the new alerts are provably good)

Your replay harness + telemetry already gives you the naive-vs-priority table. Extend it:

1. **Per-hazard recall/precision.** Record targeted clips: descending stairs, curbs, a head-height branch/shelf, a person walking in, a car passing. Label each clip's ground-truth hazard windows; measure **detection recall** (did it warn in time?) and **false-alarm rate**. This is the evidence that 3.1/3.2/3.3 work. High recall on drop-offs/head-height is your headline safety result.
2. **Reaction-time proxy.** Log the **time from hazard-onset to alert** in telemetry. Show earcons fire faster than sentences (supports 3.5).
3. **Cognitive-load subjective measure.** In your seated pilot, add a short **NASA-TLX** (or even a single 1–7 "mental effort" item) per mode. Pair it with the objective words-spoken count — subjective + objective load is a complete, publishable evaluation of the "Cost of Knowing" thesis.
4. **Comprehension check.** After each clip, ask the blindfolded participant "what was around you / what should you do?" and score correctness. Proves quieter ≠ less informative.

---

## 6. Suggested sequencing for the 40-day review (~2026-09-15)

| Week | Focus | Items |
|------|-------|-------|
| 1 | Refactor depth reuse + Tier-1 safety gaps | `(detections, depth_map)` refactor, **3.1 head-height**, **3.2 drop-off** |
| 2 | Decision-layer rigor | **3.3 TTC bands + vehicle priority + debounce**, **3.6 actionable gating** |
| 3 | Blind-native output | **3.4 clock-face + steps**, **3.5 earcons/spatial audio + vibrate**, **3.7 settings** |
| 4 | Evaluate + write | Section 5 hazard-recall study, NASA-TLX pilot, comprehension check, report + slides |

This is achievable because none of Tier 1–2 needs a new model or new hardware — it's decision-layer and frontend work on the stack you already run locally.

---

## 7. One-paragraph framing for your report/viva

> *Blind and low-vision travellers (2.2 B worldwide; 43 M blind) rely on the long cane, which is cheap and reliable but structurally cannot detect head-height obstacles or drop-offs — the causes of frequent head injuries and falls — and provides no semantic understanding of what an obstacle is. The dominant barrier to electronic travel aids is not sensing but **cognitive load**: alerts that add processing cost without preventing collisions actively slow users (Skovfoged et al., Proc. ACM HCI 2022). Virtual Eye addresses both gaps with a single chest-height camera: a metric-depth perception stack that specifically detects the cane's blind spots (overhead hazards, descending steps), and a **cognitive-load-aware decision layer** that ranks threats by time-to-collision using agility-personalized urgency bands, filters non-actionable obstacles, and delivers alerts in the blind traveller's own vocabulary (clock-face directions, step distances) through modality chosen by urgency (spatialized earcons for imminent danger, speech for description). We evaluate it not only on detection accuracy but on spoken-word cognitive-load and comprehension — directly measuring the trade-off the literature identifies as decisive for adoption.*

---

## Sources

**Cognitive load & alert design**
- Skovfoged, Rasmussen, Kirsh & Knoche. *The Cost of Knowing: How Obstacle Alerts Reduce Walking Speeds of Augmented White Cane Users.* Proc. ACM Hum.-Comput. Interact. 6, MHCI, Art. 192 (2022). https://doi.org/10.1145/3546727
- Li et al. *ISANA: Vision-based Mobile Indoor Assistive Navigation Aid for Blind People* (message-priority architecture; actionable vs non-actionable). https://pmc.ncbi.nlm.nih.gov/articles/PMC6371975/
- *Route Descriptions, Spatial Knowledge… Improved Design of Electronic Travel Aids.* ACM Transactions on Accessible Computing (2022). https://dl.acm.org/doi/10.1145/3549077
- *Efficacy of electronic travel aids for the blind and visually impaired during wayfinding.* Scientific Reports (2026). https://www.nature.com/articles/s41598-026-37578-9

**Cane limitations, head-height & drop-offs**
- *Assistive technology solutions for aiding travel of pedestrians with visual impairment.* J. Rehabilitation & Assistive Tech. Eng. (2017). https://journals.sagepub.com/doi/full/10.1177/2055668317725993
- *Technology-assisted white cane: evaluation and future directions.* PMC. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6292384/
- *Multimodal sensing and intuitive steering assistance…* Science Robotics. https://www.science.org/doi/10.1126/scirobotics.abg6594
- *Low-power depth-based descending stair detection for smart assistive devices.* EURASIP J. Image & Video Processing (2016). https://jivp-eurasipjournals.springeropen.com/articles/10.1186/s13640-016-0133-6

**Time-to-collision & urgency mapping**
- *Walking information provision system* (agility-personalized TTC urgency bands). US Patent. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11908316
- *ImpactAlert: Pedestrian-Carried Vehicle Collision Alert System.* Electronics/MDPI (2025). https://www.mdpi.com/2079-9292/14/15/3133
- *Visual, auditory, and audiovisual time-to-collision estimation… (TTC-AMD study).* PMC. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12677487/

**Non-speech audio: earcons / spearcons / spatial**
- Walker, Lindsay, Nance et al. *Spearcons (Speech-Based Earcons) Improve Navigation Performance in Advanced Auditory Menus.* Human Factors (2013). https://journals.sagepub.com/doi/10.1177/0018720812450587
- *Auditory icons, earcons, spearcons, and speech: A systematic review and meta-analysis of brief audio alerts.* https://www.academia.edu/94454696/
- Wilson, Walker, Lindsay et al. *SWAN: System for Wearable Audio Navigation.* ISWC 2007.

**Vibrotactile / multimodal**
- *Obstacle Detection Display for Visually Impaired: Coding of Direction, Distance, and Height on a Vibrotactile Waist Band.* Frontiers in ICT (2017). https://www.frontiersin.org/articles/10.3389/fict.2017.00023/full
- ALVU (Array of Lidars and Vibrotactile Units) — waist sensor belt + haptic strap.
- Flores et al. (2015) — tactile belt vs audio: closer path-following, positive directional ratings.

**Crosswalks / moving vehicles**
- *Mobile Accessible Pedestrian Signals (MAPS) for Blind…* Univ. of Minnesota (27% unaided-crossing figure). https://cts-d10resmod-prd.oit.umn.edu/pdf/cts-12-25.pdf
- *Assistive Systems for Visually Impaired Persons: Challenges and Opportunities for Navigation Assistance.* Sensors/MDPI (2024). https://www.mdpi.com/1424-8220/24/11/3572

**O&M conventions & wayfinding**
- *Wayfinding with Impaired Vision: Preferences for Cues, Strategies, and Aids (Parts I & II).* PMC. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12838941/ · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12839134/
- *GuideDog: A Real-World Egocentric Multimodal Dataset for Blind and Low-Vision Accessibility-Aware Guidance.* arXiv:2503.12844.

**Epidemiology**
- WHO, *Blindness and vision impairment* fact sheet (Oct 2023) & *World report on vision.* https://www.who.int/publications-detail-redirect/world-report-on-vision
- GBD Vision Loss Expert Group. *Trends in prevalence of blindness and vision impairment over 30 years.* Lancet Global Health (2021). https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7820390/
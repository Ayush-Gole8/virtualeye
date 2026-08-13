"""
Virtual Eye 3.0 Backend — INTEGRATED (Week 1 + Week 2)

Real-time assistive perception for the visually impaired.

Pipeline (all local, no Colab/ngrok):
    YOLOv8n + ByteTrack   -> detection + tracking
    Depth Anything V2     -> per-pixel METRIC depth (replaces K/bbox pinhole)
    engine.motion         -> approaching / crossing / still + velocity + TTC
    engine.color          -> dominant-colour naming
    engine.priority       -> cognitive-load-aware, TTC-ranked selection (core contribution)
    engine.path           -> clear-path / obstacle-in-corridor navigation
    engine.narrate        -> attribute-rich spoken sentences
    engine.vlm            -> Florence-2 scene Q&A + open-vocabulary 'find my X'
    engine.ocr            -> on-demand EasyOCR 'read this'
    engine.telemetry      -> JSONL logging for the naive-vs-priority user study

BLIP-2 has been fully removed. Distance now comes from the metric depth map,
so the old K calibration is legacy (endpoints kept so the frontend UI doesn't break).
"""

import os
import cv2
import time
import json
import base64
import numpy as np
import requests

import torch
from flask import Flask, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO

# Optional server-side TTS (frontend normally handles speech via Web Speech API)
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

# EasyOCR is still used directly by the /ocr, /ocr_url, /ocr_pdf endpoints
import easyocr

# ---- Perception engine (UI-free modules) --------------------------------------
from engine import depth as eng_depth
from engine import motion as eng_motion
from engine import color as eng_color
from engine import priority as eng_priority
from engine import narrate as eng_narrate
from engine import path as eng_path
from engine import vlm as eng_vlm
from engine import ocr as eng_ocr
from engine import telemetry as eng_telemetry


# ============== CONFIG ==============
MODEL_WEIGHTS = "yolov8n.pt"
CONF_THRESH = 0.35
LEFT_FRAC = 0.33
RIGHT_FRAC = 0.66
K_CALIB_FILE = "calib_K.json"
K_DEFAULT = None                       # legacy; distance now from depth map
OCR_LANG_DEFAULT = ["en"]

# Priority-engine knobs (tune these live during Days 3-5)
PRIORITY_TOP_K = 2
PRIORITY_MIN_SCORE = 4.0
USE_TTC = True

# User agility setting: "high" (default) or "low".
# "low" shifts TTC urgency thresholds earlier so warnings come sooner.
SAFETY_AGILITY_DEFAULT = "high"


# ============== FLASK APP ==============
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# ============== GLOBAL STATE ==============
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[INIT] Using device: {device}")
if torch.cuda.is_available():
    print(f"[INIT] GPU: {torch.cuda.get_device_name(0)}")
    print(f"[INIT] CUDA: {torch.version.cuda}, "
          f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    print("[INIT] Running on CPU — GPU strongly recommended.")

# YOLO
print("[INIT] Loading YOLOv8n...")
model = YOLO(MODEL_WEIGHTS)

# Depth Anything V2 (metric indoor small) — loaded once, kept warm
print("[INIT] Loading Depth Anything V2...")
eng_depth.load_depth_model(device=device)

# Florence-2 (scene Q&A + open-vocab find) — loaded once, kept warm
print("[INIT] Loading Florence-2...")
try:
    eng_vlm.load_vlm(device=device)
except Exception as e:
    print(f"[WARNING] Florence-2 failed to load: {e}. /query describe|find will be degraded.")

# EasyOCR readers are LAZY (loaded on first OCR request) so startup VRAM stays low.
# The periodic loop never touches OCR.
ocr_readers = {}

# Optional server-side TTS
tts = None
if pyttsx3 is not None:
    try:
        tts = pyttsx3.init()
        tts.setProperty("rate", 160)
        print("[INIT] Server-side TTS ready.")
    except Exception as e:
        print(f"[INIT] Server-side TTS unavailable ({e}); frontend handles speech.")

# Change-detection state for priority announce-gate: track_id -> (dist_band, motion)
_last_announced = {}


# ============== UTILITIES ==============
def load_calib_K():
    try:
        with open(K_CALIB_FILE, "r") as f:
            return json.load(f).get("K", None)
    except Exception:
        return None


def save_calib_K(K):
    with open(K_CALIB_FILE, "w") as f:
        json.dump({"K": K}, f)


def choose_side(cx, w):
    if cx < w * LEFT_FRAC:
        return "left"
    if cx > w * RIGHT_FRAC:
        return "right"
    return "center"


def encode_image_base64(image_array):
    _, buffer = cv2.imencode('.jpg', image_array)
    return base64.b64encode(buffer).decode('utf-8')


def get_ocr_reader(langs):
    """Lazy-load + cache an EasyOCR reader for the requested language list."""
    key = tuple(langs)
    if key in ocr_readers:
        return ocr_readers[key]
    try:
        reader = easyocr.Reader(langs, gpu=torch.cuda.is_available(), verbose=False)
        ocr_readers[key] = reader
        print(f"[OCR] Loaded reader for {langs}")
        return reader
    except Exception as e:
        print(f"[OCR] Failed to load reader for {langs}: {e}")
        return None


def speak(text):
    if tts is None or not text:
        return
    try:
        tts.say(text)
        tts.runAndWait()
    except Exception as e:
        print(f"[TTS] {e}")


def simple_detection_facts(frame):
    """
    Run the full perception stack on a frame.

    Returns:
        (detections, depth_map)
        detections: list of enriched dicts (class, bbox, track_id, distance,
                    distance_str, side, cx, cy, color, motion, velocity_mps, ttc)
        depth_map:  (H, W) float32 metric depth — reused by path analysis
    """
    h, w = frame.shape[:2]
    depth_map = eng_depth.compute_depth_map(frame)

    results = model.track(frame, persist=True, conf=CONF_THRESH)[0]
    detections = []
    if results.boxes is not None:
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            name = model.names[int(box.cls[0])]
            tid = int(box.id[0]) if box.id is not None else -1
            cx = (x1 + x2) // 2
            if name in eng_priority.VEHICLE_CLASSES:
                if not eng_path.plausible_vehicle_geometry(depth_map, [x1, y1, x2, y2]):
                    continue
            dist = eng_depth.object_distance_from_depth(depth_map, [x1, y1, x2, y2])
            col = eng_color.dominant_color(frame, [x1, y1, x2, y2], cls=name)

            detections.append({
                "class": name,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
                "track_id": tid,
                "distance": dist,
                "distance_str": eng_depth.format_distance(dist),
                "side": choose_side(cx, w),
                "cx": cx,
                "cy": (y1 + y2) // 2,
                "bbox_height": y2 - y1,
                "color": col,
            })

    detections = eng_motion.update_motion(detections, w)
    return detections, depth_map


def scan_terrain_hazards(depth_map):
    """
    Run overhead + drop-off + staircase detectors on an already-computed
    depth map.

    Returns:
        {
          "overhead":   <analyze_overhead result or None>,
          "dropoff":    <detect_dropoff result or None>,
          "staircase":  <detect_staircase result or None>,
          "speech":     "<hazard sentence(s), highest urgency first>" or ""
        }

    Only CONFIRMED hazards produce speech (all three detectors self-debounce
    over consecutive frames), so this will not chatter on a single noisy
    frame. Drop-off is spoken first (a fall is the higher consequence),
    then staircase, then overhead.
    """
    overhead = eng_path.analyze_overhead(depth_map)
    dropoff = eng_path.detect_dropoff(depth_map)
    staircase = eng_path.detect_staircase(depth_map)

    parts = []
    do_msg = eng_narrate.narrate_dropoff(dropoff)
    st_msg = eng_narrate.narrate_staircase(staircase)
    oh_msg = eng_narrate.narrate_overhead(overhead)
    if do_msg:
        parts.append(do_msg)
    if st_msg:
        parts.append(st_msg)
    if oh_msg:
        parts.append(oh_msg)

    return {
        "overhead": overhead if overhead.get("detected") else None,
        "dropoff": dropoff if dropoff.get("detected") else None,
        "staircase": staircase if staircase.get("detected") else None,
        "speech": " ".join(parts),
    }

def qa_from_detections(question, detections):
    """Rule-based fallback Q&A over detection facts (no model call)."""
    if not detections:
        return "I don't see anything clearly in view."
    q = question.lower()

    if any(k in q for k in ["what is here", "what do you see", "what is around", "describe"]):
        names = list(dict.fromkeys(d["class"] for d in detections))
        return f"I see: {', '.join(names)}."

    for keyword in ["how many", "count", "number of"]:
        if keyword in q:
            target = next((w for w in q.split()
                           if w.isalpha() and w not in ["how", "many", "count", "of"]), None)
            if target:
                n = sum(1 for d in detections if target in d["class"].lower())
                return f"I can see {n} {target}(s)."

    if any(s in q for s in ["left", "right", "front"]):
        parts = []
        for side, label in [("left", "On your left"), ("center", "In front"), ("right", "On your right")]:
            items = list(dict.fromkeys(d["class"] for d in detections if d["side"] == side))
            if items:
                parts.append(f"{label}: {', '.join(items)}")
        return "; ".join(parts) if parts else "I don't have a clear side-based view yet."

    names = list(dict.fromkeys(d["class"] for d in detections))
    return f"I see: {', '.join(names)}."


# ============== ENDPOINTS ==============

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "device": device})


@app.route('/analyze_frame', methods=['POST'])
def analyze_frame():
    """
    Periodic narration loop.

    Body (multipart/form-data):
        frame       : image file
        mode        : 'naive' | 'priority'  (default 'priority')
        session_id  : telemetry session name (default auto)
        lang        : reserved for localization
    Returns:
        detections, speech, mode, path, has_objects, annotated_image
    """
    global _last_announced
    try:
        if 'frame' not in request.files:
            return jsonify({"error": "No frame provided"}), 400

        t0 = time.perf_counter()
        file = request.files['frame']
        mode = request.form.get('mode', 'priority')
        session_id = request.form.get('session_id', '') or None

        # Agility setting controls TTC urgency band thresholds.
        # "low" agility produces earlier (more conservative) warnings.
        agility = (
            request.form.get(
                "agility",
                SAFETY_AGILITY_DEFAULT,
            )
            .strip()
            .lower()
        )
        if agility not in {"high", "low"}:
            agility = SAFETY_AGILITY_DEFAULT

        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        h, w = frame.shape[:2]

        eng_telemetry.start_session(session_id)

        detections, depth_map = simple_detection_facts(frame)

        # ------------------------------------------------------------------
        # Depth-based navigation and structural safety
        # Reuses the single depth map produced above — no extra model call.
        # ------------------------------------------------------------------

        path_verdict = eng_path.analyze_path(depth_map, w, h)
        path_changed = eng_path.should_announce_verdict(path_verdict)
        path_speech = (
            eng_narrate.narrate_path(path_changed)
            if path_changed
            else ""
        )

        # 3.1 Head-height / upper-body hazard alert
        overhead_result = eng_path.analyze_overhead(depth_map)
        overhead_speech = eng_narrate.narrate_overhead(overhead_result)

        # 3.2 Descending stair / curb / drop-off warning
        dropoff_result = eng_path.detect_dropoff(depth_map)
        dropoff_speech = eng_narrate.narrate_dropoff(dropoff_result)

        # ------------------------------------------------------------------
        # Object speech: naive (announce all) vs priority (TTC-ranked, gated)
        # 3.3 agility is threaded into the priority engine here.
        # ------------------------------------------------------------------

        if mode == 'naive':
            # Baseline: announce every detected object without filtering.
            # This branch intentionally omits TTC/priority to preserve the
            # naive-vs-priority study baseline.
            object_speech = ". ".join(
                f"{d['class']} on your {d['side']}, {d['distance_str']} away"
                for d in detections
            )
            speak_dets = detections
        else:
            top = eng_priority.prioritize(
                detections,
                w,
                top_k=PRIORITY_TOP_K,
                min_score=PRIORITY_MIN_SCORE,
                use_ttc=USE_TTC,
                agility=agility,      # 3.3: propagates high/low TTC bands
            )
            changed = [
                d for d in top
                if eng_priority.should_announce_now(
                    d, d['track_id'], _last_announced
                )
            ]
            object_speech = (
                eng_narrate.narrate(changed)
                if changed
                else ""
            )
            speak_dets = top
        staircase_result = eng_path.detect_staircase(depth_map)
        if staircase_result.get("detected") and staircase_result.get("roi"):
            r = staircase_result["roi"]
            staircase_result["color"] = eng_color.dominant_color(
                frame, [r["x0"], r["y0"], r["x1"], r["y1"]]
            )
        staircase_speech = eng_narrate.narrate_staircase(staircase_result)
        # ------------------------------------------------------------------
        # Structured alert list for Tier-2 frontend consumption.
        # Drop-off is CRITICAL, overhead is HIGH.
        # Both are always included so the frontend can render all hazards.
        # ------------------------------------------------------------------

        alerts = []

        if dropoff_result.get("detected", False):
            alerts.append({
                "type": "dropoff",
                "priority": "critical",
                "speech": dropoff_speech,
                "distance_m": dropoff_result.get("distance_m"),
                "confidence": dropoff_result.get("confidence", 0.0),
            })

        if overhead_result.get("detected", False):
            alerts.append({
                "type": "overhead",
                "priority": "high",
                "speech": overhead_speech,
                "distance_m": overhead_result.get("distance_m"),
                "confidence": overhead_result.get("confidence", 0.0),
            })

        if staircase_result.get("detected", False):
            alerts.append({
                "type": "staircase",
                "priority": "high",
                "speech": staircase_speech,
                "distance_m": staircase_result.get("distance_m"),
                "confidence": staircase_result.get("confidence", 0.0),
            })

        # ------------------------------------------------------------------
        # Safety speech priority policy:
        #   drop-off (critical) > overhead (high) > path/objects
        #
        # Only the single highest-priority structural event enters the
        # spoken channel to avoid auditory overload at the worst moments.
        # The full `alerts` list is still returned in the JSON response.
        # ------------------------------------------------------------------

        structural_speech = ""
        if dropoff_speech:
            structural_speech = dropoff_speech
        elif staircase_speech:
            structural_speech = staircase_speech
        elif overhead_speech:
            structural_speech = overhead_speech

        if structural_speech:
            speech = structural_speech
        else:
            speech = " ".join(
                s for s in [path_speech, object_speech] if s
            ).strip()

        # ------------------------------------------------------------------
        # Build response_detections: JSON-safe copy with explicit urgency
        # field so the frontend doesn't need to interpret urgency_band.
        # ------------------------------------------------------------------

        response_detections = []
        for d in detections:
            item = dict(d)
            # urgency_band is written by compute_priority_score;
            # expose it as "urgency" for the frontend.
            item["urgency"] = item.get("urgency_band", "none")
            response_detections.append(item)

        # --- Annotate frame for the debug overlay ---
        for d in speak_dets:
            x1, y1, x2, y2 = d["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{d['class']} {d['distance_str']}", (x1, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        cv2.line(frame, (int(w * LEFT_FRAC), 0), (int(w * LEFT_FRAC), h), (255, 255, 0), 1)
        cv2.line(frame, (int(w * RIGHT_FRAC), 0), (int(w * RIGHT_FRAC), h), (255, 255, 0), 1)
        annotated_b64 = encode_image_base64(frame)

        # --- Telemetry (expanded for Tier-1 evaluation) ---
        latency_ms = (time.perf_counter() - t0) * 1000.0

        det_records = []
        for d in detections:
            det_records.append({
                "class": d.get("class"),
                "track_id": d.get("track_id"),
                "dist_m": d.get("distance"),
                "side": d.get("side"),
                "motion": d.get("motion"),
                "velocity_mps": d.get("velocity_mps"),
                "closing_speed_mps": d.get("closing_speed_mps"),
                "ttc_s": d.get("ttc"),
                "urgency": d.get("urgency_band", "none"),
                "ttc_decreasing": d.get("ttc_decreasing", False),
                "ttc_high_confirmed": d.get("ttc_high_confirmed", False),
                "priority": d.get("priority"),
            })

        eng_telemetry.log_frame({
            "ts": time.time(),
            "session": eng_telemetry.current_session(),
            "mode": mode,
            "agility": agility,
            "latency_ms": round(latency_ms, 1),
            "n_dets": len(detections),
            "dets": det_records,
            "alerts": alerts,
            "overhead": overhead_result,
            "dropoff": dropoff_result,
            "staircase": staircase_result,
            "path": path_verdict,
            "path_changed": path_changed is not None,
            "speech": speech,
            "words": len(speech.split()) if speech else 0,
        })

        return jsonify({
            "detections": response_detections,
            "speech": speech,
            "mode": mode,
            "agility": agility,
            "path": path_verdict,
            "overhead": overhead_result,
            "dropoff": dropoff_result,
            "staircase": staircase_result,
            "alerts": alerts,
            "has_objects": len(detections) > 0,
            "annotated_image": annotated_b64,
            "K_value": K_DEFAULT,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[analyze_frame] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/query', methods=['POST'])
def query():
    """
    On-demand voice Q&A.

    Body (multipart/form-data):
        frame  : image file
        intent : 'describe' | 'find' | 'read'
        target : object name (for 'find'), e.g. 'water bottle'
    """
    try:
        if 'frame' not in request.files:
            return jsonify({"error": "No frame provided"}), 400
        file = request.files['frame']
        intent = request.form.get('intent', 'describe')

        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        w = frame.shape[1]

        if intent == 'read':
            text = eng_ocr.read_text(frame, min_conf=0.25, detail=0)
            return jsonify({"speech": eng_narrate.narrate_read(text), "text": text})

        if intent == 'find':
            target = request.form.get('target', 'object')
            detections, depth_map = simple_detection_facts(frame)
            matches = [d for d in detections if target.lower() in d['class'].lower()]
            if matches:
                best = max(matches, key=lambda d: (d['bbox'][2] - d['bbox'][0]) * (d['bbox'][3] - d['bbox'][1]))
                speech = eng_narrate.narrate_find(target, best['bbox'], best['side'], best['distance'])
            else:
                r = eng_vlm.find_object(frame, target)
                if r['found']:
                    side = choose_side(r['cx'], w)
                    dist = eng_depth.object_distance_from_depth(depth_map, r['bbox'])
                    speech = eng_narrate.narrate_find(target, r['bbox'], side, dist)
                else:
                    speech = eng_narrate.narrate_find(target, None, None, None)
            return jsonify({"speech": speech})

        # describe
        speech = eng_vlm.describe_scene(frame)
        return jsonify({"speech": speech})

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[query] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/question', methods=['POST'])
def ask_question():
    """Rule-based Q&A over detections (kept for backward compatibility)."""
    try:
        if 'frame' not in request.files or 'question' not in request.form:
            return jsonify({"error": "Missing frame or question"}), 400
        file = request.files['frame']
        question = request.form['question']

        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400

        if any(k in question.lower() for k in ["describe", "what do you see", "what is here"]):
            answer = eng_vlm.describe_scene(frame)
        else:
            detections, _ = simple_detection_facts(frame)
            answer = qa_from_detections(question, detections)
        return jsonify({"question": question, "answer": answer})

    except Exception as e:
        print(f"[question] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/telemetry/stop', methods=['POST'])
def stop_telemetry():
    """Flush + close the current study log (call when a trial ends)."""
    eng_telemetry.stop_session()
    return jsonify({"status": "stopped"})


# -------- Legacy calibration endpoints (distance now uses depth; kept for UI) --------
@app.route('/calibrate', methods=['POST'])
def calibrate():
    global K_DEFAULT
    try:
        if 'frame' not in request.files or 'distance_m' not in request.form:
            return jsonify({"error": "Missing frame or distance_m"}), 400
        file = request.files['frame']
        dist_m = float(request.form['distance_m'])
        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        res = model(frame)[0]
        best_h = max((int(r.xyxy[0][3] - r.xyxy[0][1]) for r in res.boxes), default=0)
        if best_h <= 0:
            return jsonify({"error": "No object detected for calibration"}), 400
        K_DEFAULT = dist_m * best_h
        save_calib_K(K_DEFAULT)
        return jsonify({"success": True, "K": K_DEFAULT, "bbox_height": best_h, "distance_m": dist_m})
    except Exception as e:
        print(f"[calibrate] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_calib_K', methods=['GET'])
def get_calib_K():
    return jsonify({"K": K_DEFAULT, "is_calibrated": K_DEFAULT is not None})


@app.route('/reset_calib', methods=['POST'])
def reset_calib():
    global K_DEFAULT
    K_DEFAULT = None
    try:
        os.remove(K_CALIB_FILE)
    except Exception:
        pass
    return jsonify({"success": True, "K": None})


# -------- OCR endpoints (image / URL / PDF) — lazy readers --------
@app.route('/ocr', methods=['POST'])
def ocr():
    if 'frame' not in request.files:
        return jsonify({"error": "No frame provided"}), 400
    try:
        file = request.files['frame']
        langs = [s.strip() for s in request.form.get("langs", "").split(",") if s.strip()] or OCR_LANG_DEFAULT
        langs = langs[:3]
        reader = get_ocr_reader(langs)
        if reader is None:
            return jsonify({"error": f"OCR unavailable for {langs}"}), 503
        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        max_side = max(frame.shape[:2])
        if max_side > 1280:
            scale = 1280 / max_side
            frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(cv2.equalizeHist(gray), 3)
        results = reader.readtext(gray)
        lines = [r[1] for r in results if r and len(r) >= 2]
        return jsonify({"success": True, "text": "\n".join(lines).strip(),
                        "line_count": len(lines), "languages": langs})
    except Exception as e:
        print(f"[ocr] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/ocr_url', methods=['POST'])
def ocr_url():
    if 'url' not in request.form:
        return jsonify({"error": "No URL provided"}), 400
    try:
        image_url = request.form['url']
        langs = [s.strip() for s in request.form.get("langs", "").split(",") if s.strip()] or OCR_LANG_DEFAULT
        langs = langs[:3]
        reader = get_ocr_reader(langs)
        if reader is None:
            return jsonify({"error": f"OCR unavailable for {langs}"}), 503
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(image_url, timeout=15, stream=True, headers=headers, allow_redirects=True)
        resp.raise_for_status()
        img_array = np.frombuffer(resp.content, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Could not decode image from URL"}), 400
        max_side = max(frame.shape[:2])
        if max_side > 1280:
            scale = 1280 / max_side
            frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(cv2.equalizeHist(gray), 3)
        results = reader.readtext(gray)
        lines = [r[1] for r in results if r and len(r) >= 2]
        return jsonify({"success": True, "text": "\n".join(lines).strip(),
                        "line_count": len(lines), "languages": langs})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch image: {e}"}), 400
    except Exception as e:
        print(f"[ocr_url] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/ocr_pdf', methods=['POST'])
def ocr_pdf():
    if 'pdf' not in request.files:
        return jsonify({"error": "No PDF file provided"}), 400
    try:
        pdf_file = request.files['pdf']
        langs = [s.strip() for s in request.form.get("langs", "").split(",") if s.strip()] or OCR_LANG_DEFAULT
        langs = langs[:3]
        reader = get_ocr_reader(langs)
        if reader is None:
            return jsonify({"error": f"OCR unavailable for {langs}"}), 503
        pdf_bytes = pdf_file.read()
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=5, dpi=200)
            all_text = []
            for i, img in enumerate(images):
                frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.medianBlur(cv2.equalizeHist(gray), 3)
                results = reader.readtext(gray)
                page_text = [r[1] for r in results if r and len(r) >= 2]
                if page_text:
                    all_text.append(f"--- Page {i+1} ---\n" + "\n".join(page_text))
            return jsonify({"success": True, "text": "\n\n".join(all_text).strip(),
                            "pages_processed": len(images), "languages": langs})
        except ImportError:
            return jsonify({"error": "pip install pdf2image pillow (+ poppler) for PDF OCR."}), 503
    except Exception as e:
        print(f"[ocr_pdf] {e}")
        return jsonify({"error": str(e)}), 500


def reset_all_engine_state():
    """
    Clear all temporal engine state.

    Must be called when the camera restarts or a new study session begins,
    otherwise stale motion history / TTC debounce / path streak data from
    the previous session can fire spurious hazard warnings on the first
    frame of a new session.

    Clears:
      - motion history + TTC confirmation flags  (eng_motion)
      - priority announce-gate cache             (_last_announced)
      - path/clear-path last-state               (eng_path — via reset_path_state,
                                                  which also clears _dropoff_streak)
    """
    global _last_announced
    eng_motion.reset_motion()
    eng_priority.reset_priority_state()
    eng_path.reset_path_state()   # clears BOTH path last-state AND drop-off streak
    _last_announced = {}
    print("[RESET] All engine temporal state cleared.")


@app.route('/reset', methods=['POST'])
def reset_session():
    """
    Camera-restart / study-session boundary hook.

    Call this from the frontend whenever the user starts a new navigation
    session or the camera feed is restarted, so no stale hazard state
    bleeds across sessions.
    """
    reset_all_engine_state()
    return jsonify({"status": "reset", "message": "All engine state cleared."})


# ============== MAIN ==============
if __name__ == '__main__':
    K_DEFAULT = load_calib_K()
    print(f"[INIT] Legacy K = {K_DEFAULT} (distance now from depth map)")
    print("\n[SERVER] http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

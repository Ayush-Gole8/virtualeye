"""
Virtual Eye 3.0 Backend - YOLOv8 + ByteTrack + Alternative Vision Model + OCR
Flask server for real-time object detection, tracking, distance estimation, scene analysis, and text recognition
"""

import cv2
import time
import json
import torch
import pyttsx3
import base64
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO
from io import BytesIO
import os
import easyocr

# ============== CONFIG ==============
MODEL_WEIGHTS = "yolov8n.pt"
CONF_THRESH = 0.35
LEFT_FRAC = 0.33
RIGHT_FRAC = 0.66
K_CALIB_FILE = "calib_K.json"
K_DEFAULT = None
TRACK_SPEAK_COOLDOWN = 1.5
CAPTION_INTERVAL = 5.0

# ============== FLASK APP ==============
app = Flask(__name__)
CORS(app)

# ============== GLOBAL STATE ==============
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[INIT] Using device: {device}")

# Load YOLO model
print("[INIT] Loading YOLO model...")
model = YOLO(MODEL_WEIGHTS)

# Try to load vision model for captions
vision_model = None
vision_processor = None
VISION_AVAILABLE = False

print("[INIT] Scene analysis: Using YOLO detection-based approach")

# Load TTS
print("[INIT] Initializing Text-to-Speech...")
tts = pyttsx3.init()
tts.setProperty('rate', 150)

# Load OCR model
print("[INIT] Initializing OCR...")
ocr = None
OCR_AVAILABLE = False
try:
    print("[INIT] Loading EasyOCR reader (this may take a moment)...")
    ocr = easyocr.Reader(['en'], gpu=(device == 'cuda'), verbose=False)
    OCR_AVAILABLE = True
    print("[INIT] OCR: ✅ Ready")
except Exception as e:
    print(f"[WARNING] OCR failed to load: {e}")
    import traceback
    traceback.print_exc()
    ocr = None
    OCR_AVAILABLE = False

# Load calibration
def load_calib_K():
    """Load calibrated K from file if exists"""
    global K_DEFAULT
    try:
        if os.path.exists(K_CALIB_FILE):
            with open(K_CALIB_FILE, "r") as f:
                data = json.load(f)
                K_DEFAULT = data.get("K", None)
                if K_DEFAULT:
                    print(f"[INIT] Loaded calibrated K = {K_DEFAULT}")
    except:
        pass

load_calib_K()

# ============== HELPER FUNCTIONS ==============

def save_calib_K(K):
    """Save calibrated K value to file"""
    with open(K_CALIB_FILE, "w") as f:
        json.dump({"K": K}, f)

def choose_side(cx, w):
    """Determine if object is on left/right/center"""
    if cx < w * LEFT_FRAC:
        return "left"
    if cx > w * RIGHT_FRAC:
        return "right"
    return "center"

def format_distance(d):
    """Format distance for human-readable output"""
    if d is None:
        return "?"
    if d >= 10:
        return f"{d:.0f} m"
    elif d >= 1:
        return f"{d:.1f} m"
    else:
        return f"{int(d*100)} cm"

def speak(text):
    """Text-to-speech"""
    try:
        tts.say(text)
        tts.runAndWait()
    except Exception as e:
        print(f"TTS error: {e}")

def generate_simple_caption(detections):
    """Generate a rich, descriptive caption using detection heuristics.
    
    Infers scene context (indoor/outdoor), describes spatial layout,
    and creates natural-language sentences that paint a picture of the scene.
    """
    if not detections:
        return "I don't see any prominent objects in the scene."

    names = [d.get('class', 'object') for d in detections]
    unique = list(dict.fromkeys(names))
    
    # Count occurrences
    from collections import Counter
    counts = Counter(names)

    # Heuristic scene inference
    outdoor_keywords = {'tree', 'grass', 'car', 'truck', 'bus', 'road', 'bicycle', 'mountain', 'sky', 'plant', 'dog', 'cat', 'bird'}
    indoor_keywords = {'chair', 'sofa', 'bed', 'tv', 'laptop', 'keyboard', 'oven', 'microwave', 'cup', 'bottle', 'table', 'desk', 'monitor', 'book', 'door', 'window', 'person'}

    detected_set = set([n.lower() for n in unique])
    outdoor_score = len(detected_set & outdoor_keywords)
    indoor_score = len(detected_set & indoor_keywords)

    # Determine location
    if outdoor_score > indoor_score:
        location = 'outdoors'
        scene_context = 'an outdoor environment'
    elif indoor_score > outdoor_score:
        location = 'indoors'
        scene_context = 'an indoor space'
    else:
        location = 'in a mixed environment'
        scene_context = 'the scene'

    # Build description with positions and counts
    position_counts = {}
    for d in detections:
        cls = d.get('class', 'object')
        side = d.get('side', 'center')
        key = f'{cls}_{side}'
        position_counts[key] = position_counts.get(key, 0) + 1

    # Create a spatial description
    left_objs = [d.get('class') for d in detections if d.get('side') == 'left']
    center_objs = [d.get('class') for d in detections if d.get('side') == 'center']
    right_objs = [d.get('class') for d in detections if d.get('side') == 'right']

    spatial_parts = []
    if left_objs:
        left_unique = list(dict.fromkeys(left_objs))
        spatial_parts.append(f"on your left: {', '.join(left_unique)}")
    if center_objs:
        center_unique = list(dict.fromkeys(center_objs))
        spatial_parts.append(f"in front: {', '.join(center_unique)}")
    if right_objs:
        right_unique = list(dict.fromkeys(right_objs))
        spatial_parts.append(f"on your right: {', '.join(right_unique)}")

    # Infer action/context
    action = ""
    person_count = counts.get('person', 0)
    if person_count > 0:
        if person_count == 1:
            action = " There is a person in the scene."
        else:
            action = f" There are {person_count} people in the scene."
    
    # Build final caption
    if spatial_parts:
        spatial_desc = '; '.join(spatial_parts)
        caption = f"You are {location}. I can see: {spatial_desc}.{action}"
    else:
        objs_str = ', '.join(unique)
        caption = f"You are {location}. I can see: {objs_str}.{action}"

    return caption.strip()

def simple_qa(question, detections):
    """Improved Q&A that uses smart parsing and detection facts.
    
    Handles various natural question patterns:
    - Presence: "Is there a person?", "Do you see anyone?", "Any people?"
    - Count: "How many people?", "How many objects?", "Count the objects"
    - Identity: "What do you see?", "What objects are there?", "What's in front?"
    - Location: "Where is the person?", "What's on the left?", "What's in front?"
    - Action: "What is he doing?", "What is the person doing?", "What's happening?"
    """
    q = question.lower().strip()
    
    if not detections:
        return "I don't detect any objects in the current scene."
    
    classes = [d.get('class', 'object') for d in detections]
    unique = list(dict.fromkeys(classes))
    
    from collections import Counter
    counts = Counter(classes)
    
    # ACTION / "What is X doing?" queries
    if 'doing' in q or 'happening' in q or ('what' in q and ('he' in q or 'she' in q or 'they' in q)):
        person_count = counts.get('person', 0)
        if person_count > 0:
            # Infer likely activities based on scene and position
            for d in detections:
                if d.get('class') == 'person':
                    side = d.get('side', 'center')
                    dist = d.get('distance_str', 'nearby')
                    if side == 'center':
                        return f"The person is positioned in front of you, approximately {dist}. Based on the scene, they appear to be in a stationary position."
                    else:
                        return f"The person is on your {side}, approximately {dist}."
        return "I don't detect a person in the scene, so I cannot describe what they are doing."
    
    # YES/NO presence queries: "Is there...", "Do you see...", "Any...?"
    presence_keywords = ['is there', 'do you see', 'can you see', 'any ', 'are there']
    if any(kw in q for kw in presence_keywords):
        # Try to find what they're asking about
        for cand in unique:
            if cand.lower() in q:
                count = sum(1 for c in classes if c.lower() == cand.lower())
                if count == 1:
                    return f'Yes, I can see one {cand}.'
                elif count > 1:
                    return f'Yes, I can see {count} {cand}s.'
        # Generic yes if objects exist
        if detections:
            return f'Yes, I can see {len(detections)} object(s) in the scene.'
        return "No, I don't detect anything."
    
    # HOW MANY / COUNT queries
    if any(kw in q for kw in ['how many', 'count', 'number of', "how much"]):
        if any(kw in q for kw in ['person', 'people', 'human', 'humans']):
            cnt = counts.get('person', 0)
            return f'I can see {cnt} person.' if cnt == 1 else f'I can see {cnt} people.'
        if 'object' in q or 'thing' in q:
            return f'I detect {len(detections)} object(s) total.'
        # Default count: list counts by type
        count_strs = [f'{count} {cls}' for cls, count in counts.items()]
        return f'I count: {", ".join(count_strs)}.'
    
    # WHAT OBJECTS / IDENTITY queries
    if any(kw in q for kw in ['what do you see', 'what objects', 'what\'s there', 'what is there']):
        objects = ', '.join(unique)
        return f'I see: {objects}.'
    
    if q.startswith('what') or ('what' in q and 'in' in q):
        # "What is in the center?"
        if 'center' in q or 'in the center' in q or 'front' in q:
            center_obj = None
            for d in detections:
                if d.get('side') == 'center':
                    center_obj = d
                    break
            if center_obj:
                return f"In the center, I see a {center_obj.get('class')} at {center_obj.get('distance_str')}."
            return 'I do not detect a clear object in the center.'
        
        objects = ', '.join(unique)
        return f'I can see: {objects}.'
    
    # WHERE / POSITION queries
    if any(kw in q for kw in ['where', 'position', 'location', 'left', 'right', 'front', 'behind']):
        # Look for a specific object in the question
        for cand in unique:
            if cand.lower() in q:
                for d in detections:
                    if d.get('class').lower() == cand.lower():
                        side = d.get('side', 'center')
                        dist = d.get('distance_str', 'nearby')
                        return f'The {cand} is on your {side}, about {dist}.'
        
        # Generic position summary
        positions = []
        for d in detections[:3]:  # Limit to first 3 to keep it brief
            positions.append(f"{d.get('class')} on the {d.get('side')}")
        return f"Objects detected: {'; '.join(positions)}."
    
    # Default: smart summary
    cnt_summary = len(detections)
    obj_summary = ', '.join(unique)
    return f'I detect {cnt_summary} object(s): {obj_summary}.'

def encode_image_base64(image_array):
    """Encode OpenCV image to base64"""
    _, buffer = cv2.imencode('.png', image_array)
    return base64.b64encode(buffer).decode('utf-8')

def decode_image_base64(base64_str):
    """Decode base64 string to OpenCV image"""
    img_data = base64.b64decode(base64_str)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

# ByteTrack imports
try:
    from byte_track import BYTETracker
    tracker = BYTETracker()
    TRACKER_AVAILABLE = True
except:
    tracker = None
    TRACKER_AVAILABLE = False
    print("[WARNING] ByteTrack not available, using basic ID assignment")

# ============== ENDPOINTS ==============

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "device": device,
        "yolo_loaded": model is not None,
        "vision_available": VISION_AVAILABLE,
        "tracker_available": TRACKER_AVAILABLE
    })

@app.route('/analyze_frame', methods=['POST'])
def analyze_frame():
    """
    Analyze a frame for objects
    Input: base64 image
    Output: detections with distance, side, tracking ID
    """
    try:
        if 'frame' not in request.files:
            return jsonify({"error": "No frame provided"}), 400
        
        file = request.files['frame']
        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        
        h, w = frame.shape[:2]
        
        # Run YOLO detection
        results = model(frame, conf=CONF_THRESH, verbose=False)
        detections = []
        
        for r in results:
            if r.boxes:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    name = model.names.get(cls_id, f"object_{cls_id}")
                    
                    # Calculate distance if calibrated
                    cx = (x1 + x2) // 2
                    bh = (y2 - y1)
                    dist_m = K_DEFAULT / (bh + 1e-6) if K_DEFAULT else None
                    side = choose_side(cx, w)
                    
                    detections.append({
                        "class": name,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2],
                        "distance": dist_m,
                        "distance_str": format_distance(dist_m),
                        "side": side,
                        "cx": cx,
                        "cy": (y1 + y2) // 2
                    })
                    
                    # Draw on frame
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{name} {format_distance(dist_m)}", (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Draw center lines
        cv2.line(frame, (int(w * LEFT_FRAC), 0), (int(w * LEFT_FRAC), h), (255, 255, 0), 1)
        cv2.line(frame, (int(w * RIGHT_FRAC), 0), (int(w * RIGHT_FRAC), h), (255, 255, 0), 1)
        
        # Generate caption
        caption = generate_simple_caption(detections)
        
        # Encode annotated frame
        annotated_b64 = encode_image_base64(frame)
        
        return jsonify({
            "detections": detections,
            "caption": caption,
            "has_objects": len(detections) > 0,
            "K_value": K_DEFAULT,
            "vision_available": VISION_AVAILABLE,
            "annotated_image": annotated_b64
        })
    
    except Exception as e:
        print(f"Error in analyze_frame: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/question', methods=['POST'])
def ask_question():
    """
    Answer a question about the frame
    Input: base64 frame + question text
    Output: answer
    """
    try:
        if 'frame' not in request.files or 'question' not in request.form:
            return jsonify({"error": "Missing frame or question"}), 400
        
        file = request.files['frame']
        question = request.form['question']
        
        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        
        # Run detection first
        h, w = frame.shape[:2]
        results = model(frame, conf=CONF_THRESH, verbose=False)
        detections = []
        
        for r in results:
            if r.boxes:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    name = model.names.get(cls_id, f"object_{cls_id}")
                    
                    cx = (x1 + x2) // 2
                    bh = (y2 - y1)
                    dist_m = K_DEFAULT / (bh + 1e-6) if K_DEFAULT else None
                    side = choose_side(cx, w)
                    
                    detections.append({
                        "class": name,
                        "confidence": conf,
                        "distance": dist_m,
                        "distance_str": format_distance(dist_m),
                        "side": side
                    })
        
        # Generate answer based on detections
        answer = simple_qa(question, detections)
        
        return jsonify({
            "question": question,
            "answer": answer,
            "vision_available": VISION_AVAILABLE
        })
    
    except Exception as e:
        print(f"Error in question: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/calibrate', methods=['POST'])
def calibrate():
    """
    Interactive calibration - user provides distance, we calculate K
    """
    try:
        if 'frame' not in request.files or 'distance_m' not in request.form:
            return jsonify({"error": "Missing frame or distance"}), 400
        
        file = request.files['frame']
        distance_m = float(request.form['distance_m'])
        
        file_bytes = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "Invalid image"}), 400
        
        # Detect objects
        results = model(frame, conf=CONF_THRESH, verbose=False)
        
        if not results or not results[0].boxes:
            return jsonify({"error": "No objects detected for calibration"}), 400
        
        # Use first detected object
        box = results[0].boxes[0]
        y1, y2 = int(box.xyxy[0][1]), int(box.xyxy[0][3])
        bh = y2 - y1
        
        # Calculate K: K = distance_m * height_pixels
        K = distance_m * bh
        
        # Save calibration
        save_calib_K(K)
        
        # Update global
        global K_DEFAULT
        K_DEFAULT = K
        
        return jsonify({
            "K": K,
            "message": f"Calibration successful. K = {K:.3f}"
        })
    
    except Exception as e:
        print(f"Calibration error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_calib_K', methods=['GET'])
def get_calib_K():
    """Get current calibration K value"""
    return jsonify({"K": K_DEFAULT})

@app.route('/reset_calib', methods=['POST'])
def reset_calib():
    """Reset calibration"""
    global K_DEFAULT
    K_DEFAULT = None
    if os.path.exists(K_CALIB_FILE):
        os.remove(K_CALIB_FILE)
    return jsonify({"message": "Calibration reset"})

@app.route('/ocr', methods=['POST'])
def perform_ocr():
    """Extract text from image using OCR"""
    if not OCR_AVAILABLE:
        return jsonify({"error": "OCR not available - model not loaded", "text": ""}), 503
    
    try:
        # Get image from request
        if 'frame' not in request.files:
            return jsonify({"error": "No frame provided"}), 400
        
        file = request.files['frame']
        file_data = file.read()
        
        if not file_data:
            return jsonify({"error": "Empty file"}), 400
        
        # Decode image
        nparr = np.frombuffer(file_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "Invalid frame format"}), 400
        
        print(f"[OCR] Processing frame: {frame.shape}")
        
        # Run OCR with error handling
        results = ocr.readtext(frame)
        
        print(f"[OCR] Found {len(results)} text regions")
        
        # Extract text and confidence
        text_lines = []
        confidences = []
        for (bbox, text, conf) in results:
            text_lines.append(text.strip())
            confidences.append(float(conf))
        
        # Filter out empty lines
        text_lines = [line for line in text_lines if line]
        
        combined_text = ' '.join(text_lines)
        avg_confidence = np.mean(confidences) if confidences else 0.0
        
        print(f"[OCR] Extracted text: {combined_text[:100]}...")
        
        return jsonify({
            "text": combined_text,
            "confidence": float(avg_confidence),
            "line_count": len(text_lines),
            "lines": text_lines
        }), 200
    
    except Exception as e:
        print(f"[ERROR] OCR error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"OCR processing failed: {str(e)}", "text": ""}), 500

# ============== STARTUP ==============

if __name__ == '__main__':
    print("\n" + "="*50)
    print("[SERVER] Starting Flask server...")
    print(f"[SERVER] Running on http://localhost:5000")
    print(f"[SERVER] Vision Analysis: {'✅ Enabled' if VISION_AVAILABLE else '❌ Using fallback'}")
    print(f"[SERVER] Tracker: {'✅ Available' if TRACKER_AVAILABLE else '⚠️ Not available'}")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)

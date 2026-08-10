# Virtual Eye 3.0 - Testing Guide

## Pre-Flight Checklist

### Prerequisites
- [ ] Python 3.8+ installed
- [ ] Node.js 16+ installed
- [ ] Webcam connected and accessible
- [ ] Microphone connected (for voice)
- [ ] At least 8GB RAM
- [ ] Stable internet connection (for model downloads)

### First Time Setup
- [ ] Backend server starts without errors
- [ ] Frontend loads on localhost:5173
- [ ] Camera access is granted
- [ ] No CORS errors in browser console

---

## Phase 1: Backend Testing

### 1.1 Server Startup
```bash
cd backend
pip install -r requirements.txt
python server.py
```

**Expected Output:**
```
[INIT] Using device: cuda  (or cpu)
[INIT] Loading YOLO model...
[INIT] Loading BLIP-2 model...
[SERVER] Starting Flask server...
[SERVER] Running on http://localhost:5000
```

**Test:**
```bash
curl http://localhost:5000/health
```

**Expected Response:**
```json
{"status": "ok", "device": "cuda"}
```

### 1.2 Model Download
- [ ] YOLOv8n.pt downloads automatically on first run
- [ ] BLIP-2 model downloads from Hugging Face (~10GB)
- [ ] No authentication errors
- [ ] Models cached locally for future runs

### 1.3 API Connectivity
Test each endpoint:

```bash
# Health check
curl http://localhost:5000/health

# Calibration status
curl http://localhost:5000/get_calib_K

# Reset calibration
curl -X POST http://localhost:5000/reset_calib
```

---

## Phase 2: Frontend Testing

### 2.1 Application Loading
```bash
npm install
npm run dev
```

**Expected Output:**
```
  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

**Test:**
- [ ] Landing page loads
- [ ] Navbar renders correctly
- [ ] Features section visible
- [ ] Mic orb button present
- [ ] No console errors

### 2.2 Navigation
Test each route:
- [ ] "/" - Landing page loads
- [ ] "/dashboard" - Dashboard accessible
- [ ] "/dashboard/vision" - Vision page loads
- [ ] "/dashboard/demopurpose" - Demo page loads
- [ ] Sidebar navigation works

### 2.3 Browser Compatibility
- [ ] Chrome/Chromium ✅
- [ ] Edge ✅
- [ ] Firefox (Web Speech API may not work)
- [ ] Safari ✅

---

## Phase 3: Camera & Detection Testing

### 3.1 Camera Access
1. Navigate to Vision page
2. Click "Start Camera"
3. **Verify:**
   - [ ] Camera feed appears
   - [ ] Video mirrors correctly (scaleX(-1))
   - [ ] No black screen
   - [ ] FPS indicator (if visible)

### 3.2 Object Detection
1. Point camera at objects (person, chair, laptop, etc.)
2. **Verify:**
   - [ ] Bounding boxes appear around objects
   - [ ] Class labels visible (person, chair, book, etc.)
   - [ ] Confidence scores display
   - [ ] Updates every 2.5 seconds
   - [ ] No lag or freezing

### 3.3 Detection Visualization
1. Wait for object detection
2. **Verify:**
   - [ ] Green bounding boxes draw correctly
   - [ ] Text labels appear with class names
   - [ ] Multiple objects detected simultaneously
   - [ ] Annotated image displays in analysis panel
   - [ ] Detection list updates in real-time

---

## Phase 4: Distance Calibration Testing

### 4.1 Pre-Calibration State
1. Open Vision page
2. **Verify:**
   - [ ] Yellow warning message shows: "Distance calibration recommended"
   - [ ] Distances show "?" before calibration
   - [ ] No distance estimates in detection list

### 4.2 Calibration Process
1. Place object at known distance (e.g., 2.5m)
2. Click "Calibrate" button
3. Enter distance (2.5)
4. System captures frame
5. **Verify:**
   - [ ] Calibration panel appears
   - [ ] Input field accepts numeric values
   - [ ] Success message shows K value
   - [ ] Green success indicator appears
   - [ ] Calibration saved (check backend logs)

### 4.3 Post-Calibration
1. Point camera at various distances
2. **Verify:**
   - [ ] Distances display (e.g., "2.5 m", "150 cm")
   - [ ] Distance formatting works (>10m, >1m, <1m)
   - [ ] Accuracy is reasonable
   - [ ] Detection side (left/right/center) works
   - [ ] K value persists after page reload

### 4.4 Calibration Reset
1. Click "Recalibrate" button
2. Press new calibration
3. **Verify:**
   - [ ] Old K value replaced
   - [ ] Distances recalculate
   - [ ] Accuracy improves with new calibration

---

## Phase 5: Voice Command Testing

### 5.1 Voice Recognition Setup
1. Click on page or mic orb (wakes up audio context)
2. Press Spacebar
3. **Verify:**
   - [ ] Listening indicator appears
   - [ ] System speaks "I am listening"
   - [ ] Mic orb shows active state (blue pulse)

### 5.2 Test Each Command

#### Camera Commands
```
Voice: "Start camera"
Expected: Camera starts, frame analysis begins

Voice: "Stop camera"
Expected: Camera stops, analysis stops

Voice: "Capture"
Expected: Single frame analysis triggered
```

#### Calibration Commands
```
Voice: "Calibrate"
Expected: Opens calibration panel, speaks instruction

Voice: "Set distance"
Expected: Same as above (alternative phrasing)
```

#### Q&A Commands
```
Voice: "Ask what color is the car"
Expected: Q&A panel opens, awaits question

Voice: "Question"
Expected: Q&A panel opens
```

#### Navigation Commands
```
Voice: "Vision"
Expected: Navigates to Vision page

Voice: "Dashboard"
Expected: Navigates to Dashboard

Voice: "Exit"
Expected: Navigates to Landing page
```

### 5.3 Voice Feedback
1. Speak any command
2. **Verify:**
   - [ ] System acknowledges with speech
   - [ ] Appropriate action occurs
   - [ ] No speech overlap/interruption

---

## Phase 6: Distance Estimation Testing

### 6.1 Calibration Accuracy
**Setup:** Place object at 2.5m distance

1. Calibrate with exact distance
2. Measure detected bbox height: H pixels
3. K = 2.5 × H
4. Move camera to new distance: 5m
5. New bbox height: H' pixels
6. Calculated distance: K / H' should ≈ 5m

**Verify:**
- [ ] Formula works: distance = K / height
- [ ] Accuracy ±20% acceptable
- [ ] Works for near (1m) and far (10m)

### 6.2 Side Detection
1. Move object to left third of screen
2. **Verify:** Side shows "left"
3. Move to center
4. **Verify:** Side shows "center"
5. Move to right
6. **Verify:** Side shows "right"

---

## Phase 7: Q&A Testing

### 7.1 Q&A Functionality
1. Open Vision page
2. Click "Ask AI" button
3. Type question: "What color is the wall?"
4. **Verify:**
   - [ ] Q&A panel opens
   - [ ] Question input field active
   - [ ] Submit button clickable

### 7.2 AI Responses
1. Ask various questions:
   - "What's in this image?"
   - "How many people?"
   - "What time is it?"
   - "Describe the scene"

2. **Verify:**
   - [ ] Responses are contextually relevant
   - [ ] No errors or timeouts
   - [ ] Answer displays in panel
   - [ ] Audio plays response

### 7.3 Question Accuracy
- [ ] Factual questions answered correctly
- [ ] Scene descriptions are accurate
- [ ] No hallucinations or nonsense
- [ ] Handles ambiguous questions gracefully

---

## Phase 8: Scene Captioning Testing

### 8.1 Automatic Captioning
1. Start camera
2. Point at scene
3. Wait for caption
4. **Verify:**
   - [ ] Caption appears every ~5 seconds
   - [ ] Description is relevant
   - [ ] Spoken aloud (if audio enabled)
   - [ ] Updates with scene changes

### 8.2 Caption Quality
Point camera at:
- [ ] Empty room → Describes empty space
- [ ] Multiple people → Counts/describes people
- [ ] Objects → Lists objects present
- [ ] Text → Attempts to read (if any)

---

## Phase 9: Voice Alerts Testing

### 9.1 Object Announcements
1. Start camera
2. Object enters frame
3. **Verify:**
   - [ ] System speaks: "Person on your left, 2.5 m away"
   - [ ] Format: "[class] on your [side], [distance] away"
   - [ ] No repeated alerts for same object

### 9.2 Alert Frequency
1. Keep same object in view
2. **Verify:**
   - [ ] Alert spoken once
   - [ ] Not repeated every frame
   - [ ] Respects TRACK_SPEAK_COOLDOWN (1.5s)

### 9.3 Multiple Objects
1. Have multiple objects in view
2. **Verify:**
   - [ ] All detected objects announced
   - [ ] Pronunciation clear
   - [ ] Order logical (left to right)

---

## Phase 10: Stress Testing

### 10.1 Prolonged Operation
1. Start camera
2. Run for 10+ minutes
3. **Verify:**
   - [ ] No memory leaks
   - [ ] No performance degradation
   - [ ] CPU/GPU usage stable
   - [ ] No connection drops

### 10.2 High-Complexity Scenes
1. Use cluttered scene (busy street, crowded room)
2. **Verify:**
   - [ ] System handles multiple objects
   - [ ] No crashes or hangs
   - [ ] Detection still accurate
   - [ ] Performance acceptable

### 10.3 Rapid Command Switching
1. Rapidly switch between camera, stop, Q&A
2. **Verify:**
   - [ ] No state confusion
   - [ ] Proper cleanup
   - [ ] No stuck processes

---

## Phase 11: Error Handling

### 11.1 Missing Camera
1. Disconnect/block camera
2. Click "Start Camera"
3. **Verify:**
   - [ ] Error message displays
   - [ ] System speaks: "I cannot access the camera"
   - [ ] Graceful failure, no crash

### 11.2 Backend Down
1. Stop Flask server
2. Try to analyze frame
3. **Verify:**
   - [ ] Error message shows
   - [ ] Appropriate message: "Network error"
   - [ ] App doesn't freeze

### 11.3 Invalid Calibration
1. Enter non-numeric distance
2. Click Calibrate
3. **Verify:**
   - [ ] Input validation works
   - [ ] Error message shows: "Please enter valid distance"
   - [ ] No server crash

### 11.4 Large Images
1. Try to analyze large/high-res image
2. **Verify:**
   - [ ] Handles gracefully
   - [ ] Resizes if needed
   - [ ] No OOM errors

---

## Phase 12: UI/UX Testing

### 12.1 Responsiveness
- [ ] Mobile view (resize to 375px width)
- [ ] Tablet view (768px width)
- [ ] Desktop view (1920px width)
- [ ] All elements visible and functional

### 12.2 Visual Design
- [ ] Colors accessible (high contrast)
- [ ] Text readable
- [ ] Buttons properly sized
- [ ] Icons render correctly
- [ ] Animations smooth

### 12.3 Accessibility
- [ ] Keyboard navigation works (Tab)
- [ ] Voice feedback clear
- [ ] Error messages obvious
- [ ] No timing-dependent interactions

---

## Performance Testing

### Load Testing
```bash
# Simple load test script
for i in {1..10}; do
    curl -X POST http://localhost:5000/analyze_frame \
        -F "frame=@test_image.jpg" \
        -F "lang=en"
done
```

### Metrics to Check
- [ ] Response time < 3 seconds
- [ ] CPU usage < 80%
- [ ] Memory stable
- [ ] No dropped frames

---

## Final Verification Checklist

### Core Features
- [ ] ✅ Object detection works
- [ ] ✅ Distance calibration works
- [ ] ✅ Distance estimation accurate
- [ ] ✅ Side detection correct
- [ ] ✅ Scene captioning works
- [ ] ✅ Q&A responses valid
- [ ] ✅ Voice commands recognized
- [ ] ✅ Voice alerts spoken

### Reliability
- [ ] ✅ No crashes during normal use
- [ ] ✅ Graceful error handling
- [ ] ✅ State management correct
- [ ] ✅ Memory leaks absent

### Usability
- [ ] ✅ Voice commands intuitive
- [ ] ✅ UI clear and responsive
- [ ] ✅ Error messages helpful
- [ ] ✅ Learning curve minimal

### Performance
- [ ] ✅ Acceptable latency
- [ ] ✅ Stable under load
- [ ] ✅ GPU accelerated (if available)
- [ ] ✅ Reasonable accuracy

---

## Test Report Template

```
Virtual Eye 3.0 - Test Report
Date: [DATE]
Tester: [NAME]
Platform: [Windows/Mac/Linux]
Hardware: [GPU/CPU]

RESULTS:
--------
Core Features: [PASS/FAIL]
  - Object Detection: [PASS/FAIL]
  - Distance Calibration: [PASS/FAIL]
  - Voice Commands: [PASS/FAIL]
  - Q&A System: [PASS/FAIL]

Reliability: [PASS/FAIL]
  - Error Handling: [PASS/FAIL]
  - Crash Testing: [PASS/FAIL]
  - State Management: [PASS/FAIL]

Performance: [PASS/FAIL]
  - Latency Acceptable: [PASS/FAIL]
  - Memory Stable: [PASS/FAIL]
  - CPU Usage Reasonable: [PASS/FAIL]

ISSUES FOUND:
--------------
[Issue 1]
[Issue 2]

RECOMMENDATIONS:
-----------------
[Recommendation 1]
[Recommendation 2]

OVERALL RESULT: [PASS/FAIL]
```

---

## Known Issues & Workarounds

### Issue: BLIP model download timeout
**Workaround:**
```bash
# Download manually
python -c "from transformers import Blip2Processor, Blip2ForConditionalGeneration; \
Blip2Processor.from_pretrained('Salesforce/blip2-opt-2.7b'); \
Blip2ForConditionalGeneration.from_pretrained('Salesforce/blip2-opt-2.7b')"
```

### Issue: Voice recognition in Firefox
**Workaround:** Use Chrome/Edge (Firefox doesn't fully support Web Speech API)

### Issue: Slow Q&A responses
**Workaround:** Use GPU acceleration or accept the latency

---

## Success Criteria

✅ All tests pass
✅ No critical bugs
✅ Acceptable performance
✅ Smooth user experience
✅ Proper error handling
✅ Clear documentation

**Status:** Ready for deployment ✅

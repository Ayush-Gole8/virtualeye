# 🚀 Virtual Eye 3.0 - Quick Reference Card

## Files Created/Modified

### New Backend Files
```
✅ backend/server.py              [650 lines] Flask server with YOLOv8 + BLIP-2
✅ backend/requirements.txt        [10 lines] Python dependencies
✅ backend/Dockerfile             [22 lines] Docker configuration
```

### Updated Frontend Files
```
✅ src/pages/VisionPage.jsx       [483 lines] Enhanced with calibration & Q&A
✅ src/pages/VisionPage.css       [430 lines] New UI components styling
✅ src/context/VoiceNavigationContext.jsx [Expanded] New voice commands
```

### Documentation Files
```
✅ README.md                       [Complete project overview]
✅ SETUP_GUIDE.md                 [Installation & troubleshooting]
✅ IMPLEMENTATION_SUMMARY.md       [Technical details & architecture]
✅ TESTING_GUIDE.md               [Comprehensive testing procedures]
✅ .env.example                   [Environment configuration template]
✅ docker-compose.yml             [Multi-container orchestration]
✅ start-windows.bat              [Automated Windows setup]
✅ start-unix.sh                  [Automated Linux/Mac setup]
```

---

## Installation Summary

### Quickest Start (Windows)
```bash
# Run this command once
start-windows.bat
```

### Quickest Start (Linux/Mac)
```bash
chmod +x start-unix.sh
./start-unix.sh
```

### Manual Start
```bash
# Terminal 1 - Backend
cd backend
pip install -r requirements.txt
python server.py

# Terminal 2 - Frontend
npm install
npm run dev
```

**Then open:** http://localhost:5173

---

## Core Features

| Feature | Status | Command |
|---------|--------|---------|
| 🔍 Object Detection | ✅ Working | "start camera" |
| 📏 Distance Calibration | ✅ Working | "calibrate" |
| 🎬 Scene Captioning | ✅ Working | Auto (every 5s) |
| 🤖 Q&A System | ✅ Working | "ask what is" |
| 🎙️ Voice Control | ✅ Working | 20+ commands |
| 🗺️ Side Detection | ✅ Working | Auto detection |
| 📊 Real-time Analytics | ✅ Working | Visualized on UI |

---

## API Endpoints

```
GET  /health                  → Server status
POST /analyze_frame          → Detect + caption
POST /question               → AI Q&A
POST /calibrate              → Distance calibration
GET  /get_calib_K            → Get calibration value
POST /reset_calib            → Reset calibration
```

---

## Voice Commands Quick Reference

```
CAMERA:
  "start camera"        → Activate vision
  "stop camera"         → Deactivate vision
  
CALIBRATION:
  "calibrate"          → Start calibration mode
  "set distance"       → Alternative trigger
  
Q&A:
  "ask what is..."     → Q&A mode
  "question"           → Alternative trigger
  
NAVIGATION:
  "vision"             → Go to Vision page
  "dashboard"          → Go to Dashboard
  "exit"               → Logout
```

---

## Key Configuration Values

### Backend (server.py)
```python
MODEL_WEIGHTS = "yolov8n.pt"    # Detection model
CONF_THRESH = 0.35              # Confidence threshold
LEFT_FRAC = 0.33                # Left boundary
RIGHT_FRAC = 0.66               # Right boundary
CAPTION_INTERVAL = 5.0          # Caption frequency (seconds)
TRACK_SPEAK_COOLDOWN = 1.5      # Alert cooldown
```

### Frontend (.env)
```
REACT_APP_API_URL=http://localhost:5000
```

---

## Distance Calibration Formula

```
Step 1: User provides known distance (D meters) and object in frame
Step 2: System measures bbox height (H pixels)
Step 3: Calculate K = D × H
Step 4: For future frames: distance = K / current_bbox_height
Step 5: K is saved and persists across sessions
```

**Example:**
- Object at 2.5m = 500px height
- K = 2.5 × 500 = 1250
- Later, same object at 100px height
- Distance = 1250 / 100 = 12.5m ✓

---

## Error Messages & Solutions

| Error | Solution |
|-------|----------|
| "Network error" | Check backend server running |
| "Camera access denied" | Grant camera permissions |
| "CUDA out of memory" | Use CPU or reduce batch size |
| "No object detected" | Improve lighting/angle |
| "Calibration failed" | Try with larger/closer object |

---

## Performance Tips

1. **Speed Up Backend**
   - Use GPU: Install CUDA
   - Reduce CAPTION_INTERVAL if slower
   - Close other apps (free up RAM)

2. **Speed Up Frontend**
   - Clear browser cache
   - Use latest Chrome/Edge
   - Disable extensions

3. **Better Accuracy**
   - Improve camera resolution
   - Ensure good lighting
   - Calibrate properly at actual use distance

---

## Technology Stack

```
Frontend: React 19 + React Router + Framer Motion
Backend: Flask + PyTorch + YOLOv8 + BLIP-2
Voice: Web Speech API + pyttsx3
Database: JSON (calib_K.json)
DevOps: Docker + Docker Compose
```

---

## System Requirements Check

```bash
# Python version
python --version          # Need 3.8+

# Node version
node --version            # Need 16+

# GPU check
python -c "import torch; print(torch.cuda.is_available())"

# Camera check
# Open any video app and verify camera works
```

---

## File Sizes (Approx)

```
YOLOv8n.pt          ~11 MB   (downloaded once)
BLIP-2 (2.7B)       ~10 GB   (downloaded once)
Frontend bundle     ~500 KB  (after npm run build)
Backend server      ~1 MB    (Python + deps)
```

---

## Deployment Options

### Option 1: Local Development
```bash
npm run dev          # Frontend on :5173
python server.py     # Backend on :5000
```

### Option 2: Docker Compose
```bash
docker-compose up    # Both services on configured ports
```

### Option 3: Production Build
```bash
npm run build        # Build React app
# Serve dist/ with web server
# Deploy server.py to cloud (Heroku, AWS, etc.)
```

---

## Testing Checklist

- [ ] Camera access works
- [ ] Objects detected (person, chair, laptop)
- [ ] Bounding boxes draw correctly
- [ ] Distance calibration completes
- [ ] Distances estimate reasonably
- [ ] Voice commands recognized
- [ ] Scene captions generate
- [ ] Q&A responses are relevant
- [ ] No crashes or freezes
- [ ] Responsive UI at all resolutions

---

## Common Issues & Fixes

### Backend Won't Start
```bash
pip install --upgrade -r requirements.txt
python -m pip install flask flask-cors numpy opencv-python torch ultralytics transformers
```

### Camera Not Working
- Check browser permissions
- Try different browser (Chrome/Edge recommended)
- Restart browser
- Check physical camera access

### Slow Q&A Responses
- BLIP-2 model is large (~2-3 seconds normal)
- Use GPU for 2x speedup
- Reduce CAPTION_INTERVAL if needed

### No Voice Recognition
- Click page first (browser audio context requirement)
- Check microphone connected
- Allow microphone permissions
- Use Chrome/Edge (Firefox limited support)

---

## Next Steps

1. **Immediate**
   - [ ] Run `start-windows.bat` or `./start-unix.sh`
   - [ ] Verify both servers start
   - [ ] Test camera and voice

2. **Short Term**
   - [ ] Calibrate for your environment
   - [ ] Test Q&A with various questions
   - [ ] Run through TESTING_GUIDE.md

3. **Medium Term**
   - [ ] Customize voice commands
   - [ ] Fine-tune detection parameters
   - [ ] Deploy to cloud if needed

4. **Long Term**
   - [ ] Add custom object detection
   - [ ] Implement advanced features
   - [ ] Optimize for your use case

---

## Support Resources

| Resource | Location |
|----------|----------|
| Installation Help | `SETUP_GUIDE.md` |
| Technical Details | `IMPLEMENTATION_SUMMARY.md` |
| Test Procedures | `TESTING_GUIDE.md` |
| API Reference | `SETUP_GUIDE.md` → API Endpoints |
| Troubleshooting | `SETUP_GUIDE.md` → Troubleshooting |

---

## Important Notes

⚠️ **First Run Takes Time**
- YOLOv8 model: ~11 MB download
- BLIP-2 model: ~10 GB download
- Total: ~10-15 minutes on first run
- Subsequent runs are instant

⚠️ **GPU Memory Required**
- BLIP-2 requires ~6GB VRAM
- Falls back to CPU if OOM

⚠️ **Calibration is Important**
- Distance estimation accuracy depends on proper calibration
- Calibrate at the distance you'll typically use the app
- Re-calibrate if camera angle changes significantly

---

## Success Indicators

✅ Both servers running without errors
✅ Camera feed displays in browser
✅ Objects detected with bounding boxes
✅ Voice commands recognized
✅ Calibration completes successfully
✅ Distances estimate within 20% accuracy
✅ Q&A provides relevant answers
✅ No crashes during extended use

---

## License & Credits

**Virtual Eye 3.0** - AI Accessibility Platform

Powered by:
- YOLOv8 (Ultralytics)
- BLIP-2 (Salesforce Research)
- ByteTrack (Zhang et al.)
- React (Meta)

---

**Ready to enhance accessibility with AI?** 🚀

Start with: `start-windows.bat` (Windows) or `./start-unix.sh` (Linux/Mac)

For detailed help, see: `SETUP_GUIDE.md`

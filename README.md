# 🎯 Virtual Eye 3.0 - AI-Powered Vision Assistant

## Overview

**Virtual Eye 3.0** is an advanced AI-powered vision assistance system designed for the visually impaired. It combines cutting-edge computer vision (YOLOv8), object tracking (ByteTrack), scene understanding (BLIP-2), and voice interaction to provide comprehensive real-world awareness.

### Key Features

🔍 **Real-Time Object Detection**
- YOLOv8 neural network for accurate object detection
- ByteTrack for persistent object tracking across frames
- Confidence scores and class labels

📏 **Distance Estimation**
- Interactive K-calibration system
- Automatic distance calculation from object size
- Formatted output (meters/centimeters)

🎬 **Scene Understanding**
- BLIP-2 vision-language model for scene captioning
- Interactive Q&A about what the camera sees
- AI-powered contextual understanding

🎙️ **Voice Interface**
- Full voice control with 20+ commands
- Text-to-speech for all alerts and responses
- Voice-based calibration and Q&A
- Real-time object announcements with distance and location

🗺️ **Spatial Awareness**
- Left/Right/Center detection
- Side indicators for object location
- Optimal for navigation guidance

---

## Quick Start

### Option 1: Automated Setup (Windows)
```bash
# Double-click this file
start-windows.bat
```

### Option 2: Automated Setup (Linux/macOS)
```bash
chmod +x start-unix.sh
./start-unix.sh
```

### Option 3: Manual Setup
```bash
# Terminal 1: Backend
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python server.py

# Terminal 2: Frontend
npm install
npm run dev
```

Then open your browser to `http://localhost:5173`

---

## System Requirements

### Minimum
- Python 3.8+
- Node.js 16+
- 8GB RAM
- Webcam

### Recommended
- GPU (NVIDIA with CUDA support)
- 12GB+ RAM
- High-speed internet (for model downloads)

### Supported Platforms
- ✅ Windows 10/11
- ✅ macOS 11+
- ✅ Linux (Ubuntu 20.04+)

---

## Architecture

### Backend (Python Flask)
```
┌─────────────────────────────────────────┐
│      Flask Web Server (localhost:5000)   │
├─────────────────────────────────────────┤
│ • YOLOv8 Detection Engine              │
│ • ByteTrack Object Tracking            │
│ • BLIP-2 Vision-Language Model         │
│ • Text-to-Speech (pyttsx3)             │
│ • Calibration Manager                  │
└─────────────────────────────────────────┘
         ↕ HTTP REST API
┌─────────────────────────────────────────┐
│    React SPA (localhost:5173)            │
├─────────────────────────────────────────┤
│ • Real-Time Camera Feed                │
│ • Detection Visualization              │
│ • Voice Commands (Web Speech API)      │
│ • Interactive Calibration UI           │
│ • Q&A Interface                        │
└─────────────────────────────────────────┘
```

---

## Usage Guide

### 1. Starting the Vision Analysis

**Voice Command:**
```
User: "Start camera"
System: Opens Vision page and activates camera
System: Announces detected objects: "Person on your left, 2.5 meters away"
```

**Manual:**
1. Click "Vision" in sidebar
2. Click "Start Camera" button
3. System analyzes frames every 2.5 seconds

### 2. Calibration (Required for Distances)

**Voice Command:**
```
User: "Calibrate"
System: Activates calibration mode
User: "2.5" (distance in meters to a visible object)
System: Captures frame, calculates distance factor
System: "Calibration successful"
```

**Manual:**
1. Position a known object at a measured distance
2. Click "Calibrate" button
3. Enter distance in meters (e.g., 2.5)
4. System learns distance calculation factor

### 3. Q&A Mode

**Voice Command:**
```
User: "Ask what color is the car"
System: Opens Q&A panel, listens for question
User: (or System recognizes): "What color is the car?"
System: "The car is blue"
```

**Manual:**
1. Start camera and point at scene
2. Click "Ask AI" button
3. Type or speak your question
4. AI analyzes the scene and responds

### 4. Voice Commands Reference

| Command | Action |
|---------|--------|
| "start camera" | Start live analysis |
| "stop camera" | Stop camera stream |
| "calibrate" | Enter calibration mode |
| "ask" / "question" | Enter Q&A mode |
| "capture" / "analyze" | Single frame analysis |
| "vision" / "camera" | Navigate to Vision page |
| "dashboard" / "home" | Go to Dashboard |
| "exit" / "logout" | Exit application |

---

## Configuration

### Backend Settings (backend/server.py)
```python
MODEL_WEIGHTS = "yolov8n.pt"      # YOLOv8 Nano (fastest)
CONF_THRESH = 0.35                # Detection confidence threshold (0-1)
LEFT_FRAC = 0.33                  # Left boundary percentage
RIGHT_FRAC = 0.66                 # Right boundary percentage
CAPTION_INTERVAL = 5.0            # Scene caption generation interval
```

### Frontend Settings (.env)
```
REACT_APP_API_URL=http://localhost:5000
```

---

## API Documentation

### Real-Time Analysis
```
POST /analyze_frame
Content-Type: multipart/form-data

Request:
{
  "frame": <binary image>,
  "lang": "en"
}

Response:
{
  "detections": [
    {
      "class": "person",
      "confidence": 0.95,
      "distance": 2.5,
      "distance_str": "2.5 m",
      "side": "left"
    }
  ],
  "caption": "A person standing in a park",
  "annotated_image": "<base64 encoded>"
}
```

### Question Answering
```
POST /question
Content-Type: multipart/form-data

Request:
{
  "frame": <binary image>,
  "question": "What color is the car?"
}

Response:
{
  "question": "What color is the car?",
  "answer": "The car is blue"
}
```

### Distance Calibration
```
POST /calibrate
Content-Type: multipart/form-data

Request:
{
  "frame": <binary image>,
  "distance_m": 2.5
}

Response:
{
  "success": true,
  "K": 1250.5,
  "bbox_height": 500
}
```

See `SETUP_GUIDE.md` for complete API documentation.

---

## Performance Benchmarks

| Task | GPU (NVIDIA) | CPU |
|------|--------------|-----|
| YOLOv8 Detection | 30-50ms | 100-200ms |
| BLIP Captioning | 1000-1500ms | 2000-3000ms |
| Q&A Response | 1000-2000ms | 2000-4000ms |
| Frame Analysis | 2.5s interval | 2.5s interval |

---

## Troubleshooting

### Issue: Backend won't start
```bash
# Check Python version
python --version

# Reinstall dependencies
cd backend
pip install --upgrade -r requirements.txt

# Check for CUDA errors
python -c "import torch; print(torch.cuda.is_available())"
```

### Issue: Camera access denied
- **Windows**: Check Settings > Privacy > Camera
- **macOS**: System Preferences > Security & Privacy > Camera
- **Linux**: `sudo usermod -a -G video $USER`

### Issue: BLIP model too slow
- BLIP-2 requires significant VRAM (~6GB)
- If OOM error: Use smaller model or CPU
- Edit server.py to use different BLIP variant

### Issue: Voice recognition not working
- Click anywhere on page first (browser audio context requirement)
- Check microphone permissions
- Ensure browser supports Web Speech API (Chrome, Edge recommended)

See `SETUP_GUIDE.md` for detailed troubleshooting.

---

## Project Structure

```
Virtual Eye/
├── backend/                   # Flask backend
│   ├── server.py             # Main server code
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile            # Docker configuration
│   └── calib_K.json          # Calibration data
├── src/                       # React application
│   ├── pages/
│   │   ├── VisionPage.jsx    # Detection interface
│   │   ├── Demo.jsx          # Image upload demo
│   │   ├── LandingPage.jsx   # Landing page
│   │   └── DashboardHome.jsx # Dashboard home
│   ├── components/
│   │   └── layout/           # Layout components
│   ├── context/              # React context
│   │   └── VoiceNavigationContext.jsx
│   ├── App.jsx               # Main app component
│   └── App.css               # Global styles
├── docker-compose.yml         # Multi-container setup
├── package.json              # Frontend dependencies
├── SETUP_GUIDE.md            # Installation guide
├── IMPLEMENTATION_SUMMARY.md # Technical details
└── README.md                 # This file
```

---

## Technology Stack

### Backend
- **Flask** - Web framework
- **PyTorch** - Deep learning framework
- **Ultralytics YOLOv8** - Object detection
- **Transformers (BLIP-2)** - Vision-language model
- **OpenCV** - Image processing
- **pyttsx3** - Text-to-speech

### Frontend
- **React 19** - UI framework
- **React Router** - Navigation
- **Framer Motion** - Animations
- **Web Speech API** - Voice recognition
- **Canvas API** - Image processing

### DevOps
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration

---

## Development

### Running in Development Mode
```bash
# Backend
cd backend
python server.py

# Frontend (new terminal)
npm run dev
```

### Building for Production
```bash
# Frontend
npm run build

# Backend (Docker)
docker build -t virtualeye:latest backend/
docker-compose up -d
```

---

## Contributing

We welcome contributions! Areas for improvement:
- [ ] Multi-language support
- [ ] Custom model training
- [ ] Mobile app
- [ ] Edge deployment (TensorFlow Lite)
- [ ] Real-time performance optimization

---

## Performance Optimization Tips

1. **Use GPU** - Install CUDA for 3-5x speedup
2. **Reduce analysis interval** - Faster feedback (adjust in code)
3. **Use lighter model** - YOLOv8n is already optimized
4. **Batch processing** - Process multiple frames together
5. **Cache predictions** - Reuse recent detections

---

## Accessibility Features

✅ Voice-first interface
✅ High contrast visuals
✅ Audio feedback for all actions
✅ Keyboard navigation
✅ Screen reader compatible
✅ Adjustable speech rate
✅ Multi-language support (ready)

---

## Known Limitations

- Requires calibration for accurate distances
- BLIP-2 model requires ~6GB VRAM
- Voice recognition needs good microphone
- Camera resolution affects detection accuracy
- Real-time processing has latency

---

## Future Roadmap

### Version 3.1
- Real-time obstacle avoidance
- Improved multi-object tracking
- Gesture recognition

### Version 3.2
- Mobile app (iOS/Android)
- Edge deployment (Raspberry Pi)
- Custom model training UI

### Version 3.3
- Multi-user support
- Cloud sync
- Advanced analytics

---

## License

Virtual Eye 3.0 - Accessibility through AI

---

## Support & Contact

For issues, questions, or feature requests:
1. Check `SETUP_GUIDE.md` troubleshooting
2. Review `IMPLEMENTATION_SUMMARY.md` for technical details
3. Check browser console (F12) for error messages
4. Check backend logs in terminal

---

## Acknowledgments

Built with:
- YOLOv8 by Ultralytics
- BLIP-2 by Salesforce Research
- ByteTrack by Zhang et al.
- React ecosystem
- Open source community

---

**Making the world accessible through AI** 🌍👀🤖

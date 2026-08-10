# Virtual Eye 3.0 - Setup Guide

## Features Implemented

### Backend (Python - Flask)
- **YOLOv8 Object Detection** - Real-time object detection with confidence scores
- **ByteTrack Integration** - Persistent object tracking across frames
- **Distance Estimation** - Interactive K calibration for accurate distance calculation
- **BLIP-2 Scene Captioning** - AI-powered scene understanding and description
- **BLIP-2 Q&A** - Answer questions about what the camera sees
- **Text-to-Speech** - Voice alerts for detected objects and distances

### Frontend (React)
- **Real-time Detection Visualization** - Bounding boxes and object information
- **Side Detection** - Objects identified as left/right/center
- **Distance Display** - Formatted distance measurements (meters/centimeters)
- **Interactive Calibration UI** - Visual interface for distance calibration
- **Voice Q&A Interface** - Ask questions about the scene
- **Voice Commands** - Extended voice control for all new features
- **Responsive Design** - Works on desktop and mobile

## Installation

### 1. Backend Setup (Python)

#### Prerequisites
- Python 3.8+
- pip

#### Steps

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/Scripts/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download YOLO model (automatic on first run, or manually)
# python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Start the server
python server.py
```

The Flask server will run on `http://localhost:5000`

### 2. Frontend Setup (React)

```bash
# Install dependencies (if not already done)
npm install

# Configure backend URL (optional, defaults to localhost:5000)
# Create .env file in root directory:
echo REACT_APP_API_URL=http://localhost:5000 > .env

# Start the development server
npm run dev
```

The React app will run on `http://localhost:5173`

## Usage

### Voice Commands

| Command | Action |
|---------|--------|
| "start camera" / "describe surroundings" | Start camera analysis |
| "stop camera" | Stop camera |
| "capture" / "analyze" | Single frame analysis |
| "calibrate" / "set distance" | Start calibration mode |
| "ask" / "question" | Start Q&A mode |
| "vision" | Navigate to Vision page |
| "dashboard" / "home" | Return to dashboard |
| "exit" / "logout" | Exit application |

### Manual Usage

1. **Start Camera**: Click "Start Camera" button or say "start camera"
2. **View Detections**: Real-time objects appear in the analysis panel
3. **Check Distances**: 
   - Ensure calibration is done first
   - Distances will show in meters or centimeters
4. **Calibrate**: 
   - Click "Calibrate" button
   - Place a known object at a measured distance
   - Enter the distance in meters
   - System learns the camera's distance factor
5. **Ask Questions**: 
   - Click "Ask AI" button
   - Ask any question about the scene
   - AI will answer based on what it sees

## API Endpoints

### POST `/analyze_frame`
Analyze a frame for objects, captions, and distances

**Request:**
```json
{
  "frame": <binary image data>,
  "lang": "en" | "hi" | "mr"
}
```

**Response:**
```json
{
  "detections": [
    {
      "class": "person",
      "confidence": 0.95,
      "bbox": [x1, y1, x2, y2],
      "distance": 2.5,
      "distance_str": "2.5 m",
      "side": "left" | "right" | "center"
    }
  ],
  "caption": "A person walking in a park",
  "annotated_image": "<base64 encoded image>"
}
```

### POST `/question`
Ask AI a question about the frame

**Request:**
```json
{
  "frame": <binary image data>,
  "question": "What color is the car?"
}
```

**Response:**
```json
{
  "question": "What color is the car?",
  "answer": "The car is blue."
}
```

### POST `/calibrate`
Calibrate distance factor K

**Request:**
```json
{
  "frame": <binary image data>,
  "distance_m": 2.5
}
```

**Response:**
```json
{
  "success": true,
  "K": 1250.5,
  "bbox_height": 500,
  "distance_m": 2.5
}
```

### GET `/get_calib_K`
Get current calibration value

**Response:**
```json
{
  "K": 1250.5,
  "is_calibrated": true
}
```

### POST `/reset_calib`
Reset calibration

**Response:**
```json
{
  "success": true,
  "K": null
}
```

### GET `/health`
Health check

**Response:**
```json
{
  "status": "ok",
  "device": "cuda" | "cpu"
}
```

## Requirements

### Hardware Requirements
- **GPU** (recommended): NVIDIA GPU with CUDA support for better performance
- **CPU** (minimum): Will work but slower
- **RAM**: 8GB+ recommended for smooth BLIP-2 processing

### Software Requirements
See `backend/requirements.txt` for exact versions

Key packages:
- Flask 3.0.0
- PyTorch 2.0.1
- Ultralytics 8.0.202 (YOLOv8)
- Transformers 4.35.2 (BLIP-2)
- OpenCV 4.8.0.74

## Troubleshooting

### Backend Issues

**"Module not found" errors**
```bash
pip install --upgrade -r requirements.txt
```

**CUDA/GPU not detected**
```bash
# Force CPU mode or reinstall PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**BLIP model too large/OOM errors**
- Uses 2.7B parameter model - requires ~6GB VRAM
- Use CPU if CUDA memory insufficient
- Edit `server.py` to use smaller models if needed

**Camera not accessible**
```bash
# Check camera permissions
# On Linux: sudo usermod -a -G video $USER
# On macOS: Allow camera access in System Preferences
# On Windows: Check Settings > Privacy > Camera
```

### Frontend Issues

**"Cannot reach backend" error**
- Ensure Flask server is running on port 5000
- Check REACT_APP_API_URL in .env file
- CORS should be enabled (it is in server.py)

**Image not showing in analysis section**
- Check browser console for CORS errors
- Ensure Flask server is accessible
- Try clearing browser cache

**Voice not working**
- Ensure microphone is connected and permitted
- Check browser privacy settings
- Try clicking anywhere on the page first (audio context requirement)

## Performance Tips

1. **GPU Acceleration**
   - Using CUDA significantly improves speed
   - YOLO detection: ~30-50ms per frame
   - BLIP captioning: ~1-2 seconds per frame

2. **Optimization**
   - YOLOv8 Nano model used (fastest)
   - BLIP-2 OPT-2.7B used (smallest)
   - Frame analysis every 2.5 seconds (adjustable)

3. **Network Latency**
   - Local backend reduces latency
   - For remote deployment, consider Edge AI

## Future Enhancements

- [ ] Multi-language scene captions
- [ ] Custom object classes training
- [ ] Edge deployment (TensorFlow Lite)
- [ ] Real-time audio feedback optimization
- [ ] Mobile app version
- [ ] Offline mode support

## Support & Debugging

Enable detailed logging:
```bash
# In Flask app, uncomment debug logs
export FLASK_ENV=development
python server.py
```

Check logs:
- Flask server console output
- Browser DevTools console
- Network tab for API calls

## License

Virtual Eye 3.0 - Built for accessibility

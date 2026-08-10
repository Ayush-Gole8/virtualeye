# Virtual Eye 3.0 - System Architecture

## Overview
Virtual Eye 3.0 is an AI-powered vision assistance system designed for visually impaired users, combining real-time computer vision, natural language understanding, and voice interaction.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐                 │
│  │  Vision Page     │  │   OCR Page       │  │  Dashboard       │                 │
│  │  (Live Camera)   │  │  (Text Reader)   │  │  (Home)          │                 │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘                 │
│                                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐               │
│  │                    Voice Navigation Context                       │               │
│  │  • Speech Recognition (Web Speech API)                            │               │
│  │  • Text-to-Speech (Web Speech Synthesis)                         │               │
│  │  • Voice Commands Processing                                      │               │
│  └──────────────────────────────────────────────────────────────────┘               │
│                                                                                       │
│  Entities: Visually Impaired Users, Caregivers, Developers                          │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    ↕ HTTP/REST API
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND SERVER LAYER (Flask)                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          API Endpoints                                        │   │
│  ├─────────────────────────────────────────────────────────────────────────────┤   │
│  │  • /health              - Server health check                                │   │
│  │  • /analyze_frame        - Real-time object detection & scene analysis        │   │
│  │  • /question            - AI Q&A about the scene                              │   │
│  │  • /calibrate           - Distance calibration                                │   │
│  │  • /get_calib_K         - Get calibration value                               │   │
│  │  • /reset_calib         - Reset calibration                                   │   │
│  │  • /ocr                 - Text extraction from images                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    ↕ Model Calls
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      AI/ML MODELS & PROCESSING LAYER                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    Computer Vision Models                                    │   │
│  ├─────────────────────────────────────────────────────────────────────────────┤   │
│  │  • YOLOv8 (Object Detection)                                                 │   │
│  │    - Real-time object detection                                              │   │
│  │    - 80+ object classes                                                      │   │
│  │    - Confidence threshold filtering                                           │   │
│  │                                                                               │   │
│  │  • ByteTrack (Object Tracking)                                               │   │
│  │    - Persistent object tracking across frames                                 │   │
│  │    - Track ID assignment                                                     │   │
│  │    - Prevents duplicate alerts                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │              Vision-Language Models (BLIP-2)                                 │   │
│  ├─────────────────────────────────────────────────────────────────────────────┤   │
│  │  • BLIP-2 Flan-T5 XL (Primary)                                               │   │
│  │    - Scene captioning                                                        │   │
│  │    - Question answering                                                      │   │
│  │    - Note/document description                                               │   │
│  │    - Contextual understanding                                                │   │
│  │                                                                               │   │
│  │  • BLIP-2 OPT-2.7B (Fallback)                                                │   │
│  │    - Alternative model if primary fails                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    Text Recognition (OCR)                                     │   │
│  ├─────────────────────────────────────────────────────────────────────────────┤   │
│  │  • EasyOCR                                                                    │   │
│  │    - Multi-language support (English, Hindi, Marathi)                        │   │
│  │    - Text extraction from images                                             │   │
│  │    - Preprocessing (grayscale, histogram equalization)                        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    Navigation & Safety Features                               │   │
│  ├─────────────────────────────────────────────────────────────────────────────┤   │
│  │  • Wall Detection                                                            │   │
│  │    - Edge detection (Canny)                                                  │   │
│  │    - Vertical line detection (Hough Transform)                               │   │
│  │    - Distance estimation                                                     │   │
│  │    - BLIP caption analysis (wall mentions)                                   │   │
│  │                                                                               │   │
│  │  • Distance Estimation                                                       │   │
│  │    - K-calibration system                                                    │   │
│  │    - Bounding box height analysis                                            │   │
│  │    - Format: meters/centimeters                                              │   │
│  │                                                                               │   │
│  │  • Spatial Awareness                                                         │   │
│  │    - Left/Right/Center detection                                             │   │
│  │    - Position-based alerts                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    ↕ Data Flow
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         DATA STORAGE & CONFIGURATION                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐                 │
│  │  Calibration     │  │  Model Weights   │  │  Configuration   │                 │
│  │  Data            │  │  Storage         │  │  Files           │                 │
│  │  (calib_K.json)  │  │  (yolov8n.pt)    │  │  (server.py)      │                 │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘                 │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Functions & Features

### Frontend Layer (React Application)

#### Vision Page
- **Real-time Camera Feed**
  - WebRTC camera access
  - Frame capture and streaming
  - Video display with annotations

- **Object Detection Visualization**
  - Bounding box overlay
  - Detection cards with details
  - Confidence scores
  - Distance display
  - Side indicators (left/right/center)

- **Interactive Features**
  - Calibration panel
  - Q&A interface
  - Language selection (EN/HI/MR)
  - Voice command integration

#### OCR Page
- **Text Extraction**
  - Camera-based text reading
  - Multi-language OCR
  - Text-to-speech output
  - Result display

#### Voice Navigation Context
- **Speech Recognition**
  - Continuous listening
  - Command processing
  - Navigation routing

- **Text-to-Speech**
  - Scene descriptions
  - Object announcements
  - Alert notifications
  - Q&A responses

---

### Backend Layer (Flask Server)

#### Core Services

**1. Frame Analysis Service**
- Receives image frames from frontend
- Processes through YOLOv8 + ByteTrack
- Generates BLIP-2 captions
- Detects walls and obstacles
- Calculates distances
- Returns annotated results

**2. Question Answering Service**
- Accepts questions about scene
- Uses BLIP-2 for detailed answers
- Falls back to detection-based answers
- Handles action queries
- Describes notes/documents

**3. Calibration Service**
- Interactive K-value calibration
- Distance factor calculation
- Persistent storage
- Calibration status tracking

**4. OCR Service**
- Multi-language text extraction
- Image preprocessing
- Text line extraction
- Language detection

**5. Wall Detection Service**
- Edge detection (Canny algorithm)
- Vertical line analysis (Hough Transform)
- Distance estimation
- Position determination
- BLIP caption analysis (for wall mentions)
- Alert generation with cooldown

---

### AI/ML Models Layer

#### YOLOv8 Object Detection
- **Functions:**
  - Real-time object detection
  - 80+ COCO classes
  - Confidence filtering
  - Bounding box extraction
  - Class identification

#### ByteTrack Object Tracking
- **Functions:**
  - Persistent object tracking
  - Track ID assignment
  - Frame-to-frame continuity
  - Duplicate detection prevention

#### BLIP-2 Vision-Language Model
- **Functions:**
  - Scene captioning
  - Question answering
  - Note/document description
  - Contextual understanding
  - Action recognition
  - Detailed scene descriptions

#### EasyOCR Text Recognition
- **Functions:**
  - Multi-language OCR
  - Text line extraction
  - Character recognition
  - Language detection
  - Image preprocessing

---

### Navigation & Safety Features

#### Wall Detection
- **Functions:**
  - Edge detection (Canny)
  - Vertical line detection (Hough)
  - Distance estimation
  - Position analysis (left/center/right)
  - Alert generation
  - 3-second cooldown system

#### Distance Estimation
- **Functions:**
  - K-calibration system
  - Bounding box analysis
  - Distance calculation
  - Format conversion (m/cm)
  - Calibration persistence

#### Spatial Awareness
- **Functions:**
  - Left/Right/Center detection
  - Position-based alerts
  - Navigation guidance
  - Obstacle positioning

---

## Data Flow

```
User (Camera) 
    ↓
Frontend (React)
    ↓ [HTTP POST /analyze_frame]
Backend (Flask)
    ↓
YOLOv8 Detection → ByteTrack Tracking
    ↓
BLIP-2 Captioning
    ↓
Wall Detection
    ↓
Distance Calculation
    ↓
Response (JSON)
    ↓
Frontend Display + TTS
    ↓
User (Audio Feedback)
```

---

## Integration Points

### External Services
- **Google Colab (GPU)**
  - Backend server hosting
  - GPU acceleration
  - Model inference

- **ngrok Tunnel**
  - Public URL generation
  - HTTPS tunneling
  - Remote access

### Browser APIs
- **Web Speech API**
  - Speech recognition
  - Text-to-speech

- **MediaDevices API**
  - Camera access
  - Video streaming

- **Canvas API**
  - Image processing
  - Frame capture

---

## Deployment Architecture

### Development
```
Local Machine (Frontend)
    ↕ HTTP
Google Colab (Backend + GPU)
    ↕ ngrok
Public Internet
```

### Production (Future)
```
CDN (Frontend)
    ↕ HTTPS
Cloud Server (Backend)
    ↕ GPU Instance
Database (Config/Calibration)
```

---

## Security & Privacy

- **Data Privacy:**
  - No data storage of images
  - Local processing preferred
  - Secure API communication

- **Access Control:**
  - Camera permission management
  - CORS configuration
  - API authentication (future)

---

## Performance Optimization

- **Model Optimization:**
  - Lighter BLIP-2 variant (Flan-T5 XL)
  - YOLOv8 Nano (fastest)
  - GPU acceleration
  - Model caching

- **Response Time:**
  - Frame analysis: 2.5s interval
  - BLIP captioning: ~1-2s
  - OCR: ~1-3s
  - Wall detection: <100ms

---

## Scalability Considerations

- **Horizontal Scaling:**
  - Multiple backend instances
  - Load balancing
  - Model serving optimization

- **Edge Deployment:**
  - Mobile app version
  - Raspberry Pi support
  - TensorFlow Lite models

---

**Virtual Eye 3.0 - Making the world accessible through AI** 🌍👀🤖


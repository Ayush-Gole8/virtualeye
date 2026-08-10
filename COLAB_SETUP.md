# Google Colab Setup with ngrok

This guide helps you run the Virtual Eye backend on Google Colab with **free GPU** and ngrok tunnel. Perfect if your laptop doesn't have a working GPU!

## Why Google Colab?

- ✅ **Free GPU access** (T4 GPU with ~15GB VRAM)
- ✅ No need to install CUDA/PyTorch on your laptop
- ✅ Faster model loading and inference
- ✅ Perfect for running BLIP-2 and YOLOv8

## Step 1: Enable GPU in Colab

1. Open Google Colab: https://colab.research.google.com
2. Create a new notebook
3. **Enable GPU Runtime:**
   - Click `Runtime` → `Change runtime type`
   - Set `Hardware accelerator` to **GPU** (T4)
   - Click `Save`
4. Verify GPU is available (run in a cell):
   ```python
   !nvidia-smi
   ```

## Step 2: Get ngrok Auth Token

1. Sign up at https://ngrok.com (free account works)
2. Get your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
3. Copy the token (you'll need it in Step 3)

## Step 3: Upload Backend Files

Upload your `backend` folder to Colab:
- Click folder icon on left sidebar
- Click "Upload" and select your `backend` folder
- Or zip it first and use: `!unzip backend.zip`

## Step 4: Run Setup Cell

Create a new cell and paste this code:

```python
# Install dependencies
!pip install -q flask flask-cors ultralytics transformers==4.41.2 tokenizers==0.15.0 pyttsx3 Pillow scipy python-dotenv requests timm easyocr pdf2image
!pip install -q pyngrok

# Install PyTorch with CUDA (for GPU support)
!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install poppler-utils for PDF processing
!apt-get update -qq
!apt-get install -y -qq poppler-utils

# Setup ngrok (replace YOUR_NGROK_TOKEN with your actual token)
from pyngrok import ngrok
import os

# Get your ngrok token from: https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_TOKEN = "YOUR_NGROK_TOKEN"  # ⚠️ REPLACE THIS WITH YOUR TOKEN

ngrok.set_auth_token(NGROK_TOKEN)

# Start ngrok tunnel on port 5000
public_url = ngrok.connect(5000)
print("=" * 50)
print("✅ ngrok tunnel created!")
print(f"🌐 Public URL: {public_url}")
print("=" * 50)
print("\n⚠️ COPY THIS URL AND USE IT IN YOUR FRONTEND .env FILE")
print(f"   VITE_API_URL={public_url}")
print("=" * 50)
```

**Important:** Replace `YOUR_NGROK_TOKEN` with your actual ngrok authtoken!

## Step 5: Run Server Cell

Create another cell and run:

```python
import os
os.chdir('/content/backend')  # Adjust path if your backend folder is elsewhere

# Verify GPU is being used
import torch
print(f"✅ CUDA Available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"✅ GPU: {torch.cuda.get_device_name(0)}")

# Start the Flask server
!python server.py
```

**Important:** 
- Keep this cell running! The server must stay active.
- You'll see GPU info and model loading progress
- The server will start on port 5000

## Step 6: Configure Frontend

1. In your local project, create a `.env` file in the root directory:
   ```
   VITE_API_URL=https://xxxx-xx-xx-xx-xx.ngrok.io
   ```
   (Replace with the ngrok URL from Colab)

2. Restart your frontend:
   ```bash
   npm run dev
   ```

## Troubleshooting

### GPU Issues
- **No GPU detected**: Make sure you selected GPU runtime (Step 1). Check with `!nvidia-smi`
- **Out of memory**: The lighter BLIP-2 Flan-T5 model should work on T4 GPU. If issues persist, the server will fall back to detection-only mode.

### ngrok Issues
- **ngrok URL changes**: Colab sessions reset after ~90 min of inactivity. Update your `.env` file when URL changes.
- **Connection refused**: Make sure the server cell is still running. Restart it if needed.

### Port Issues
- **Port 5000 busy**: Change port in `server.py` (line 550) and update ngrok: `ngrok.connect(5001)`

### Model Loading
- **BLIP-2 fails to load**: First download can take 5-10 minutes. Be patient. The server will use detection-only mode as fallback.
- **Slow first request**: Models load on first use. Subsequent requests are faster.

## Quick Copy-Paste Version

For a single cell setup (after uploading backend folder):

```python
# Complete setup in one cell
!pip install -q flask flask-cors ultralytics transformers==4.41.2 tokenizers==0.15.0 pyttsx3 Pillow scipy python-dotenv requests timm easyocr pyngrok
!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")  # ⚠️ REPLACE THIS
public_url = ngrok.connect(5000)
print(f"🌐 Use this URL: {public_url}")

import os
os.chdir('/content/backend')
!python server.py
```


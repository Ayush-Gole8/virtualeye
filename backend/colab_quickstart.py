"""
Quick Start Script for Google Colab
Copy-paste this entire script into a Colab cell after enabling GPU runtime.

Before running:
1. Enable GPU: Runtime → Change runtime type → GPU
2. Get ngrok token from: https://dashboard.ngrok.com/get-started/your-authtoken
3. Upload your backend folder to /content/backend
"""

# ========== CONFIGURATION ==========
NGROK_TOKEN = "YOUR_NGROK_TOKEN_HERE"  # ⚠️ REPLACE WITH YOUR TOKEN
BACKEND_PATH = "/content/backend"  # Adjust if your folder is elsewhere
# ===================================

import subprocess
import sys
import os

print("🚀 Virtual Eye - Google Colab Quick Start")
print("=" * 60)

# Step 1: Install dependencies
print("\n[1/4] Installing dependencies...")
packages = [
    "flask==3.0.0",
    "flask-cors==4.0.0",
    "ultralytics==8.0.202",
    "transformers==4.41.2",
    "tokenizers==0.15.0",
    "pyttsx3==2.90",
    "Pillow==10.0.0",
    "scipy==1.11.2",
    "python-dotenv==1.0.0",
    "requests==2.31.0",
    "timm==0.9.10",
    "easyocr==1.7.1",
    "pdf2image==1.16.3",
    "pyngrok",
]

for pkg in packages:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

# Install PyTorch with CUDA
print("[1/4] Installing PyTorch with CUDA...")
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "torch", "torchvision", "torchaudio",
    "--index-url", "https://download.pytorch.org/whl/cu118"
])

# Install poppler-utils for PDF processing
print("[1/4] Installing poppler-utils for PDF support...")
subprocess.check_call([
    "apt-get", "update", "-qq"
])
subprocess.check_call([
    "apt-get", "install", "-y", "-qq", "poppler-utils"
])

# Step 2: Verify GPU
print("\n[2/4] Checking GPU...")
import torch
if torch.cuda.is_available():
    print(f"✅ GPU Detected: {torch.cuda.get_device_name(0)}")
    print(f"✅ CUDA Version: {torch.version.cuda}")
    print(f"✅ GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    print("⚠️ No GPU detected! Enable GPU runtime: Runtime → Change runtime type → GPU")
    print("   The server will run on CPU (slower)")

# Step 3: Setup ngrok
print("\n[3/4] Setting up ngrok tunnel...")
try:
    from pyngrok import ngrok
    
    if NGROK_TOKEN == "YOUR_NGROK_TOKEN_HERE":
        print("⚠️ ERROR: Please set NGROK_TOKEN at the top of this script!")
        print("   Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken")
        raise ValueError("NGROK_TOKEN not set")
    
    ngrok.set_auth_token(NGROK_TOKEN)
    public_url = ngrok.connect(5000)
    
    print("=" * 60)
    print("✅ NGROK TUNNEL CREATED!")
    print(f"🌐 Public URL: {public_url}")
    print("=" * 60)
    print("\n⚠️ COPY THIS URL AND ADD TO YOUR FRONTEND .env FILE:")
    print(f"   VITE_API_URL={public_url}")
    print("=" * 60)
except Exception as e:
    print(f"❌ ngrok setup failed: {e}")
    print("   Make sure you set NGROK_TOKEN correctly")

# Step 4: Start server
print("\n[4/4] Starting Flask server...")
print("=" * 60)
print("⚠️ Keep this cell running! The server will start below.")
print("=" * 60)

# Change to backend directory
if os.path.exists(BACKEND_PATH):
    os.chdir(BACKEND_PATH)
    print(f"✅ Changed to: {os.getcwd()}")
else:
    print(f"⚠️ Backend folder not found at: {BACKEND_PATH}")
    print("   Make sure you uploaded the backend folder to Colab")
    print("   Current directory: {os.getcwd()}")

# Start server (this will block)
print("\n🚀 Starting server...\n")
os.system("python server.py")


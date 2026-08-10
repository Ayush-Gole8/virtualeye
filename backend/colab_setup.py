"""
Quick setup script for Google Colab
Run this in a Colab cell after uploading the backend folder
"""

import subprocess
import sys
import os

def install_dependencies():
    """Install all required packages"""
    print("[SETUP] Installing dependencies...")
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
        "pyngrok",
    ]
    
    for pkg in packages:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])
    
    # Install PyTorch with CUDA
    print("[SETUP] Installing PyTorch with CUDA...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "torch", "torchvision", "torchaudio",
        "--index-url", "https://download.pytorch.org/whl/cu118"
    ])
    print("[SETUP] ✅ Dependencies installed")

def setup_ngrok(token=None):
    """Setup ngrok tunnel"""
    try:
        from pyngrok import ngrok
        
        if token:
            ngrok.set_auth_token(token)
            print(f"[SETUP] ✅ ngrok authenticated")
        else:
            print("[SETUP] ⚠️ No ngrok token provided. Using default (may not work)")
        
        # Start tunnel
        public_url = ngrok.connect(5000)
        print("=" * 60)
        print("✅ NGROK TUNNEL CREATED!")
        print(f"🌐 Public URL: {public_url}")
        print("=" * 60)
        print("\n⚠️ COPY THIS URL AND ADD TO YOUR FRONTEND .env FILE:")
        print(f"   VITE_API_URL={public_url}")
        print("=" * 60)
        return public_url
    except Exception as e:
        print(f"[ERROR] ngrok setup failed: {e}")
        print("[INFO] You can manually install: pip install pyngrok")
        return None

if __name__ == "__main__":
    print("Virtual Eye - Colab Setup Script")
    print("=" * 60)
    
    # Install dependencies
    install_dependencies()
    
    # Setup ngrok (get token from https://dashboard.ngrok.com/get-started/your-authtoken)
    NGROK_TOKEN = os.environ.get("NGROK_TOKEN", None)
    if not NGROK_TOKEN:
        print("\n[INFO] To use ngrok, set NGROK_TOKEN environment variable")
        print("       Or call setup_ngrok('your_token_here') manually")
    else:
        setup_ngrok(NGROK_TOKEN)
    
    print("\n[SETUP] ✅ Setup complete!")
    print("[INFO] Now run: python server.py")


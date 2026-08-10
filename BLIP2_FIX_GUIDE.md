# BLIP-2 Model Loading Error - Solution Guide

## Problem

When running `python server.py`, you get this error:

```
Exception: data did not match any variant of untagged enum ModelWrapper at line 250373 column 3
```

This is caused by a **tokenizer compatibility issue** between the Transformers library version and the BLIP-2 model files.

---

## Quick Fix - Use Lite Server (Recommended)

The lite server skips BLIP-2 loading and works immediately:

```bash
cd backend
python server_lite.py
```

**What you get:**
- ✅ Full object detection with YOLOv8
- ✅ Distance estimation with calibration
- ✅ All voice commands work
- ✅ Side detection works
- ❌ Q&A disabled (BLIP-2 optional)
- ❌ Scene captions disabled (BLIP-2 optional)

**Frontend still works 100%** - Just shows "BLIP-2 not available" for Q&A/captions

---

## Solution 1: Fix Tokenizer (Recommended if you want BLIP-2)

```bash
# Clear transformers cache
cd backend

# Windows
if exist venv\Lib\site-packages\transformers rmdir /s /q venv\Lib\site-packages\transformers
if exist "%APPDATA%\huggingface" rmdir /s /q "%APPDATA%\huggingface"

# Mac/Linux
rm -rf venv/lib/python*/site-packages/transformers
rm -rf ~/.cache/huggingface

# Reinstall
pip install --upgrade --force-reinstall transformers==4.36.0
python server.py
```

---

## Solution 2: Use Older Working Version

```bash
pip install transformers==4.32.0 torch==2.0.1
python server.py
```

---

## Solution 3: Skip BLIP Models (Fastest)

Just use the lite server - it works without BLIP:

```bash
python server_lite.py
```

---

## What Changed

The error happens because:
1. Hugging Face released newer BLIP model files
2. Your transformers library expects older format
3. Tokenizer can't parse the JSON

**The fix:**
- Updated `server.py` with error handling
- Created `server_lite.py` that skips BLIP gracefully
- Both servers work with detection and distance estimation

---

## Verification

Run this to check what's working:

```bash
curl http://localhost:5000/health
```

**Expected response:**
```json
{
  "status": "ok",
  "device": "cpu",
  "blip_available": true,    // or false
  "yolo_loaded": true
}
```

---

## What Features Work With Each Server

| Feature | server.py | server_lite.py |
|---------|-----------|---|
| Object Detection | ✅ | ✅ |
| Distance Estimation | ✅ | ✅ |
| Calibration | ✅ | ✅ |
| Voice Commands | ✅ | ✅ |
| Side Detection | ✅ | ✅ |
| Q&A System | ✅* | ❌ |
| Scene Captions | ✅* | ❌ |

*Works if BLIP-2 loads successfully

---

## Recommended Approach

**Option A: Quick Start (Best)**
```bash
python server_lite.py
```
- Works immediately
- All core features functional
- Q&A disabled (optional feature)

**Option B: Full Features (Advanced)**
If you really need Q&A:
```bash
pip install transformers==4.32.0
python server.py
```

---

## Testing

After starting server, test with:

```bash
# Check if server is running
curl http://localhost:5000/health

# Check BLIP status
curl http://localhost:5000/health | findstr "blip_available"
```

If `"blip_available": false` and you're using `server.py`, switch to `server_lite.py`

---

## For Future: Disable BLIP at Start

If you want to skip BLIP loading entirely in `server.py`, edit it:

```python
# Find this line:
SKIP_BLIP = True  # Set to True to skip loading BLIP-2

# Then uncomment the skip logic in initialization
```

---

## Still Having Issues?

1. **Try the lite server first:** `python server_lite.py`
2. **If that works:** Your system is fine, just BLIP-2 has issues
3. **If lite also fails:** Problem is with YOLO/PyTorch (different issue)

---

**Recommendation: Use `server_lite.py` for immediate working solution!**

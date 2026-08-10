"""
On-demand OCR for the 'read this' voice intent.

Uses EasyOCR (already in the repo, en/hi/mr) to read signs, labels and medicine
boxes aloud. The Reader is lazy-loaded on the FIRST 'read' request only — it
never runs in the periodic narration loop, so the 6 GB VRAM budget on the
laptop GPU is untouched during normal use.

First call downloads EasyOCR's detection + recognition models (~100 MB, one
time, cached in ~/.EasyOCR). Hindi (hi) and Marathi (mr) are bundled at load
time; add/remove languages by editing the LOAD_LANGS list.

Citation:
JaidedAI (2020). EasyOCR: Ready-to-use OCR with 80+ supported languages.
https://github.com/JaidedAI/EasyOCR
"""

LOAD_LANGS = ["en", "hi", "mr"]

_reader = None


def _gpu_ok():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def load_ocr(gpu=True):
    """
    Lazy-load the EasyOCR Reader. Import happens inside the function so the
    periodic loop (depth + YOLO only) never pays for the OCR stack.
    """
    global _reader
    if _reader is None:
        import easyocr
        print(f"[OCR] Loading EasyOCR ({'/'.join(LOAD_LANGS)})...")
        _reader = easyocr.Reader(LOAD_LANGS, gpu=gpu and _gpu_ok(), verbose=False)
        print("[OCR] Loaded.")
    return _reader


def read_text(frame_bgr, min_conf=0.25, detail=0):
    """
    Recognize text in a BGR frame.

    Args:
        frame_bgr: OpenCV BGR image (H, W, 3) uint8
        min_conf: drop detections below this confidence (0..1)
        detail: 0 -> joined string; 1 -> list of (bbox, text, conf)

    Returns:
        detail=0: recognized text joined by spaces ("" if nothing found)
        detail=1: list of (bbox, text, conf) tuples above min_conf
    """
    reader = load_ocr()
    results = reader.readtext(frame_bgr, detail=1)
    kept = [r for r in results if r[2] >= min_conf]
    if detail == 1:
        return kept
    return " ".join(text.strip() for (_, text, _) in kept)

"""
On-demand OCR for VirtualEye's "Read Text" feature (/ocr, /ocr_url, /ocr_pdf).

This module is the SINGLE source of truth for OCR. The Flask endpoints in
server.py are thin wrappers around `recognize()`. The periodic narration loop
never imports this module, so the 6 GB VRAM budget stays free during normal
use — the EasyOCR reader is lazy-loaded on the first read request and cached
per language set.

Design (addresses the four known gaps):
  1. Preprocessing  — grayscale, upscale small frames, CLAHE contrast, edge-
                      preserving denoise, plus an adaptive-threshold variant
                      for printed labels/documents.  (was: global equalizeHist
                      + median blur only)
  2. Param tuning   — tuned EasyOCR detection/recognition params, see
                      READTEXT_PARAMS.  (was: readtext() with all defaults)
  3. Confidence     — per-line min-confidence floor + garbage rejection +
                      high-confidence fast-accept, returned in reading order.
                      (was: no confidence filtering in the live endpoints)
  4. Verification   — multi-frame OR multi-variant voting: a line must be
                      corroborated across passes unless it is already high
                      confidence, which suppresses one-off spurious reads.
                      (was: none)

Citation:
JaidedAI (2020). EasyOCR: Ready-to-use OCR with 80+ supported languages.
https://github.com/JaidedAI/EasyOCR
"""

import re
import difflib
import numpy as np
import cv2

LOAD_LANGS = ["en", "hi", "mr"]

# ----------------------------- tunables ------------------------------------
DEFAULT_MIN_CONF = 0.35    # absolute floor; a read below this is discarded
HIGH_CONF_ACCEPT = 0.60    # at/above this, accept even without cross-pass support
AGREEMENT        = 0.60    # fraction of passes a mid-conf line must appear in.
                           # 0.60 makes the 2-pass default require BOTH passes
                           # (ceil(0.6*2)=2), so multi-variant/-frame voting
                           # genuinely corroborates; a confident solo read still
                           # gets through via HIGH_CONF_ACCEPT. Larger bursts use
                           # a clear majority (5 frames -> 3, 3 frames -> 2).
UPSCALE_TARGET   = 1280    # upscale so the longest side reaches ~this (helps small text)
MAX_SIDE         = 1920    # never exceed this (bounds GPU memory / latency)
MERGE_SIMILARITY = 0.85    # near-duplicate lines above this ratio are merged when voting

# Tuned EasyOCR readtext() parameters. Tune HERE, in one place.
#   decoder='beamsearch' is a little more accurate but ~2-3x slower; 'greedy'
#   plus the preprocessing + voting below is a better latency/accuracy balance
#   for on-demand reads. text_threshold/low_text are lowered to catch fainter
#   text (the confidence filter + voting reject the extra noise this admits);
#   mag_ratio>1 upscales internally to help small/distant text.
READTEXT_PARAMS = dict(
    decoder="greedy",
    beamWidth=5,
    text_threshold=0.6,
    low_text=0.35,
    link_threshold=0.4,
    canvas_size=2560,
    mag_ratio=1.5,
    contrast_ths=0.1,
    adjust_contrast=0.7,
    add_margin=0.1,
    min_size=10,
    paragraph=False,
)

_readers = {}   # keyed by language tuple


def _gpu_ok():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def load_ocr(langs=None, gpu=True):
    """
    Lazy-load + cache an EasyOCR Reader for the requested language list.
    Import happens inside the function so the periodic loop never pays for it.
    """
    langs = list(langs) if langs else LOAD_LANGS
    key = tuple(langs)
    if key not in _readers:
        import easyocr
        print(f"[OCR] Loading EasyOCR ({'/'.join(langs)})...")
        _readers[key] = easyocr.Reader(langs, gpu=gpu and _gpu_ok(), verbose=False)
        print("[OCR] Loaded.")
    return _readers[key]


# --------------------------- preprocessing ---------------------------------
def _to_gray_bounded(frame):
    """BGR/gray -> gray, upscaling small frames and capping oversized ones."""
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    h, w = gray.shape[:2]
    m = max(h, w)
    if m < UPSCALE_TARGET:
        s = UPSCALE_TARGET / float(m)
        gray = cv2.resize(gray, (max(1, int(round(w * s))), max(1, int(round(h * s)))),
                          interpolation=cv2.INTER_CUBIC)
    elif m > MAX_SIDE:
        s = MAX_SIDE / float(m)
        gray = cv2.resize(gray, (max(1, int(round(w * s))), max(1, int(round(h * s)))),
                          interpolation=cv2.INTER_AREA)
    return gray


def _clahe(gray):
    """Adaptive (local) contrast — handles uneven lighting far better than a
    global equalizeHist, which is what the old endpoints used."""
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def preprocess(frame):
    """Primary single-pass preprocessing: bounded gray + CLAHE + light denoise."""
    gray = _to_gray_bounded(frame)
    gray = _clahe(gray)
    # bilateral filter smooths noise while preserving character edges
    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
    return gray


def preprocess_variants(frame):
    """
    Two complementary views of the same frame for multi-variant verification:
      - 'clahe'  : contrast-enhanced grayscale (best for scene / low-contrast text)
      - 'binary' : adaptive-threshold binarization (best for printed labels/docs)
    Both derive from the same bounded-gray image, so their bboxes are directly
    comparable during voting.
    """
    gray = _to_gray_bounded(frame)
    clahe = _clahe(gray)
    clahe = cv2.bilateralFilter(clahe, d=5, sigmaColor=50, sigmaSpace=50)
    binary = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
    return [("clahe", clahe), ("binary", binary)]


# ----------------------- text cleaning / filtering -------------------------
def _clean(text):
    return " ".join(str(text).split()).strip()


def _norm_key(text):
    """Loose key for voting: lowercase, alphanumerics only."""
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _looks_garbage(text, conf):
    """Reject empty / punctuation-only / lone-char / mostly-symbol shaky reads."""
    t = _clean(text)
    if not t:
        return True
    alnum = sum(ch.isalnum() for ch in t)
    if alnum == 0:                               # pure punctuation / symbols
        return True
    if len(t) == 1 and conf < 0.50:              # lone shaky character
        return True
    if alnum / len(t) < 0.40 and conf < 0.60:    # mostly symbols and not confident
        return True
    return False


def _bbox_xy(bbox):
    """EasyOCR bbox = 4 corner points -> (x_min, y_min) for reading order."""
    xs = [float(p[0]) for p in bbox]
    ys = [float(p[1]) for p in bbox]
    return min(xs), min(ys)


# --------------------------- OCR pass + voting -----------------------------
def _run_pass(img, reader, min_conf):
    """One OCR pass -> list of {text, conf, x, y} that survive the conf floor."""
    raw = reader.readtext(img, detail=1, **READTEXT_PARAMS)
    items = []
    for entry in raw:
        # detail=1, paragraph=False -> (bbox, text, conf)
        try:
            bbox, text, conf = entry[0], entry[1], float(entry[2])
        except (ValueError, TypeError, IndexError):
            continue
        text = _clean(text)
        if conf < min_conf or _looks_garbage(text, conf):
            continue
        x, y = _bbox_xy(bbox)
        items.append({"text": text, "conf": conf, "x": x, "y": y})
    return items


def _match_key(k, groups):
    """Return an existing near-duplicate key to merge into, else k itself
    (so 'aspirin' and 'asprin' from different passes count as one line)."""
    for existing in groups:
        if difflib.SequenceMatcher(None, k, existing).ratio() >= MERGE_SIMILARITY:
            return existing
    return k


def _order_reading(lines):
    """Sort top-to-bottom, then left-to-right, grouping items into rows."""
    if not lines:
        return lines
    ys = [l["y"] for l in lines]
    spread = (max(ys) - min(ys)) or 1.0
    row_tol = max(12.0, spread * 0.03)
    return sorted(lines, key=lambda l: (round(l["y"] / row_tol), l["x"]))


def _vote(passes, num_passes):
    """
    Merge OCR items from several passes (frames or variants) by voting.
    A line is accepted if it is already high-confidence OR corroborated across
    enough passes. Confidence reported is the mean over the passes that saw it.
    """
    groups = {}   # key -> {"items": [...], "passes": set()}
    for pass_idx, items in enumerate(passes):
        best_in_pass = {}
        for it in items:
            k = _norm_key(it["text"])
            if not k:
                continue
            if k not in best_in_pass or it["conf"] > best_in_pass[k]["conf"]:
                best_in_pass[k] = it
        for k, it in best_in_pass.items():
            gk = _match_key(k, groups)
            g = groups.setdefault(gk, {"items": [], "passes": set()})
            g["items"].append(it)
            g["passes"].add(pass_idx)

    need = max(1, int(np.ceil(AGREEMENT * num_passes))) if num_passes > 1 else 1
    accepted = []
    for g in groups.values():
        best = max(g["items"], key=lambda it: it["conf"])
        support = len(g["passes"])
        if best["conf"] >= HIGH_CONF_ACCEPT or support >= need:
            mean_conf = float(np.mean([it["conf"] for it in g["items"]]))
            accepted.append({"text": best["text"], "conf": round(mean_conf, 3),
                             "x": best["x"], "y": best["y"], "support": support})
    return _order_reading(accepted)


def _package(lines, langs):
    text = "\n".join(l["text"] for l in lines).strip()
    mean_conf = round(float(np.mean([l["conf"] for l in lines])), 3) if lines else 0.0
    return {
        "text": text,
        "lines": [{"text": l["text"], "conf": l["conf"]} for l in lines],
        "line_count": len(lines),
        "mean_conf": mean_conf,
        "languages": list(langs) if langs else list(LOAD_LANGS),
    }


# ------------------------------- public API --------------------------------
def recognize(frame, langs=None, min_conf=DEFAULT_MIN_CONF, verify=True):
    """
    OCR a single BGR frame.

    Returns a dict:
      {text, lines: [{text, conf}], line_count, mean_conf, languages}

    verify=True  -> multi-variant voting (CLAHE + binarized) for robustness.
    verify=False -> single fast pass (use for latency-sensitive callers).
    """
    reader = load_ocr(langs)
    if verify:
        variants = preprocess_variants(frame)
        passes = [_run_pass(img, reader, min_conf) for _, img in variants]
        merged = _vote(passes, num_passes=len(passes))
    else:
        items = _run_pass(preprocess(frame), reader, min_conf)
        merged = _vote([items], num_passes=1)
    return _package(merged, langs)


def recognize_frames(frames, langs=None, min_conf=DEFAULT_MIN_CONF):
    """
    OCR several BGR frames (e.g. a short camera burst) and keep only text
    corroborated across them. This is true multi-frame verification; callers
    that can grab a burst should prefer it over a single frame.
    """
    if not frames:
        return _package([], langs)
    reader = load_ocr(langs)
    passes = [_run_pass(preprocess(f), reader, min_conf) for f in frames]
    merged = _vote(passes, num_passes=len(passes))
    return _package(merged, langs)


def read_text(frame, min_conf=DEFAULT_MIN_CONF, detail=0, langs=None, verify=True):
    """
    Backward-compatible convenience wrapper.
      detail=0 -> joined text string ("" if nothing found)
      detail=1 -> list of {text, conf}
    """
    res = recognize(frame, langs=langs, min_conf=min_conf, verify=verify)
    return res["lines"] if detail == 1 else res["text"]

"""
Dominant color naming via HSV histogram sampling.

For a 'person' the torso region (upper-middle of the box) is sampled so we describe
clothing colour rather than background. For other objects the central patch is used.

Classical computer vision only — no model, no training. HSV colour space is used
because hue separates colour identity from lighting (value) and vividness (saturation),
which is more robust than RGB thresholds for naming.
"""

import cv2
import numpy as np

# OpenCV Hue range is 0-179. Ranges are (h_min, h_max) inclusive.
_HUE_NAMES = [
    ("red",    [(0, 9), (170, 179)]),
    ("orange", [(10, 20)]),
    ("yellow", [(21, 33)]),
    ("green",  [(34, 85)]),
    ("cyan",   [(86, 96)]),
    ("blue",   [(97, 125)]),
    ("purple", [(126, 145)]),
    ("pink",   [(146, 169)]),
]

# Saturation / Value thresholds to detect grayscale (achromatic) pixels
_MIN_SAT = 60
_MIN_VAL = 50


def _hue_to_name(hue):
    for name, ranges in _HUE_NAMES:
        for lo, hi in ranges:
            if lo <= hue <= hi:
                return name
    return None


def dominant_color(frame_bgr, bbox, cls=None):
    """
    Estimate the dominant color name inside a bounding box.

    Args:
        frame_bgr: OpenCV BGR image
        bbox: [x1, y1, x2, y2]
        cls: optional class name; if 'person', samples the torso region

    Returns:
        color name string ('red', 'blue', 'black', 'white', 'gray', ...) or None
    """
    x1, y1, x2, y2 = map(int, bbox)
    h_box = y2 - y1

    # For a person, sample the torso (roughly shoulders to waist)
    if cls == "person" and h_box > 20:
        y1s = y1 + int(0.20 * h_box)
        y2s = y1 + int(0.55 * h_box)
    else:
        # central 50% patch
        y1s = y1 + int(0.25 * h_box)
        y2s = y1 + int(0.75 * h_box)

    roi = frame_bgr[max(0, y1s):max(0, y2s), max(0, x1):max(0, x2)]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).reshape(-1, 3)

    # Split chromatic vs achromatic pixels
    chromatic = hsv[(hsv[:, 1] >= _MIN_SAT) & (hsv[:, 2] >= _MIN_VAL)]

    # If mostly achromatic, name by brightness
    if len(chromatic) < 0.25 * len(hsv):
        mean_v = float(hsv[:, 2].mean())
        if mean_v < 60:
            return "black"
        elif mean_v > 190:
            return "white"
        else:
            return "gray"

    # Otherwise use the median hue of chromatic pixels
    median_hue = int(np.median(chromatic[:, 0]))
    return _hue_to_name(median_hue)

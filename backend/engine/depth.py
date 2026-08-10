"""
Metric depth estimation using Depth Anything V2.

Citation:
Yang, L., Kang, B., Huang, Z., Zhao, Z., Xu, X., Feng, J., & Zhao, H. (2024).
Depth Anything V2. arXiv preprint arXiv:2406.09414.
https://depth-anything-v2.github.io

Model: depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf
Output: Per-pixel depth in metres (max_depth=20m for indoor scenes)
"""

import torch
import numpy as np
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
from PIL import Image
import cv2

_processor = None
_model = None
_device = None

def load_depth_model(device="cuda"):
    """
    Load Depth Anything V2 metric indoor model.

    Args:
        device: "cuda" or "cpu"

    Returns:
        (processor, model, device)
    """
    global _processor, _model, _device
    if _model is None:
        print("[DEPTH] Loading Depth Anything V2 Metric Indoor Small...")
        _device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
        _processor = AutoImageProcessor.from_pretrained(
            "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
        )
        _model = AutoModelForDepthEstimation.from_pretrained(
            "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
        )
        _model.to(_device)
        _model.eval()
        print(f"[DEPTH] Loaded on {_device}")
    return _processor, _model, _device


def compute_depth_map(frame_bgr):
    """
    Compute per-pixel depth map from a BGR frame.

    Args:
        frame_bgr: OpenCV BGR image (H, W, 3) uint8

    Returns:
        depth_map: float32 array (H, W) in metres
    """
    processor, model, device = load_depth_model()

    # Convert BGR -> RGB PIL Image
    img_rgb = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    h_orig, w_orig = frame_bgr.shape[:2]

    # Prepare input
    inputs = processor(images=img_rgb, return_tensors="pt").to(device)

    # Inference
    with torch.no_grad():
        outputs = model(**inputs)

    # Extract predicted depth
    predicted_depth = outputs.predicted_depth

    # Interpolate to original frame size
    depth_resized = torch.nn.functional.interpolate(
        predicted_depth.unsqueeze(1),
        size=(h_orig, w_orig),
        mode="bicubic",
        align_corners=False,
    )

    # Convert to numpy (H, W) in metres
    depth_map = depth_resized.squeeze().cpu().numpy()
    return depth_map


def object_distance_from_depth(depth_map, bbox):
    """
    Robust distance estimation: median depth over the central 40% of the bbox.

    Args:
        depth_map: (H, W) float array in metres
        bbox: [x1, y1, x2, y2]

    Returns:
        distance in metres (float), or None if bbox is invalid
    """
    x1, y1, x2, y2 = map(int, bbox)
    w_box, h_box = x2 - x1, y2 - y1

    # Sample central 40% patch to avoid noisy edges
    cx1 = int(x1 + 0.3 * w_box)
    cy1 = int(y1 + 0.3 * h_box)
    cx2 = int(x1 + 0.7 * w_box)
    cy2 = int(y1 + 0.7 * h_box)

    patch = depth_map[cy1:cy2, cx1:cx2]

    if patch.size == 0:
        return None

    # Median is robust to outliers
    dist = float(np.median(patch))

    # Clamp to plausible indoor range (0.2m - 20m)
    return max(0.2, min(dist, 20.0))


def format_distance(dist_m):
    """
    Format distance for speech: '1.2 m', '0.5 m', etc.
    """
    if dist_m is None:
        return "unknown distance"
    if dist_m < 1.0:
        return f"{dist_m:.1f} m"
    else:
        return f"{dist_m:.0f} m"

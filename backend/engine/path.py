"""
Clear-path navigation from the metric depth map.

Answers the blind user's actual question: "can I walk forward?" Instead of
listing objects, we analyse the depth map directly:

  - a central "walking corridor" (middle 40% of the frame width) is defined;
  - the nearest real surface inside it is found with a robust low percentile
    (a single noisy pixel must not block the path);
  - if the corridor is blocked, the left and right thirds of the frame are
    compared to advise the side with more clearance.

Pure numpy over the depth map that server.py already computes for object
distances — no model, no extra latency. Runs every frame in the periodic loop.
This replaces the old BLIP-2 "wall detect" (which died when BLIP-2 was removed).

Tunables (top of file): CORRIDOR_FRAC, BLOCKED_M, CAUTION_M, ROBUST_Q, FLOOR_BAND.
"""

import numpy as np

# Fraction of frame width covered by the walking corridor (centred)
CORRIDOR_FRAC = 0.40
# Closer than this (metres) inside the corridor => path blocked
BLOCKED_M = 2.0
# (kept for tuning: between BLOCKED_M and CAUTION_M the path is still "clear")
CAUTION_M = 3.0
# Percentile of corridor depths used as "nearest surface" (robust to noise)
ROBUST_Q = 5.0
# Bottom fraction of the frame ignored in the corridor: that band is the floor
# directly in front, which is walkable, not an obstacle. If the floor keeps
# triggering "obstacle", raise this; if low obstacles are missed, lower it.
FLOOR_BAND = 0.25

# Announce-gate state: last (band, advice) tuple, so we only speak on change
_last = None


def _valid_depths(depth_map):
    """Mask out invalid pixels (0 = unknown in Depth Anything, NaN/Inf)."""
    return np.isfinite(depth_map) & (depth_map > 0.02)


def _nearest_in_zone(depth_map, mask, x0, x1, robust_q=ROBUST_Q):
    """
    Nearest surface (metres) inside x-range [x0, x1), rows above the floor band,
    ignoring invalid pixels. Returns None if the zone has no valid depth.
    """
    rows = int(depth_map.shape[0] * (1.0 - FLOOR_BAND))
    zone = depth_map[:rows, x0:x1][mask[:rows, x0:x1]]
    if zone.size == 0:
        return None
    return float(np.percentile(zone, robust_q))


def analyze_path(depth_map, frame_w, frame_h):
    """
    Analyse a depth map for walkability.

    Args:
        depth_map: (H, W) float32 array in metres
        frame_w, frame_h: frame dimensions

    Returns:
        verdict dict:
            clear       : bool  — corridor free within BLOCKED_M
            obstacle_m  : float — nearest surface in the corridor (metres)
            advice      : str   — 'clear' | 'left' | 'right' | 'stop'
            advice_str  : str   — human phrase for the advice
    """
    del frame_h  # reserved; width defines the corridor
    mask = _valid_depths(depth_map)

    cx0 = int(frame_w * (0.5 - CORRIDOR_FRAC / 2))
    cx1 = int(frame_w * (0.5 + CORRIDOR_FRAC / 2))

    corridor_m = _nearest_in_zone(depth_map, mask, cx0, cx1)
    left_m = _nearest_in_zone(depth_map, mask, 0, int(frame_w * 0.33))
    right_m = _nearest_in_zone(depth_map, mask, int(frame_w * 0.66), frame_w)

    # No usable depth at all — be safe and say nothing specific
    if corridor_m is None:
        return {"clear": False, "obstacle_m": None, "advice": "stop",
                "advice_str": "cannot see the path ahead"}

    if corridor_m >= BLOCKED_M:
        return {"clear": True, "obstacle_m": corridor_m, "advice": "clear",
                "advice_str": "path clear"}

    # Corridor blocked: pick the side with clearly more clearance
    left_ok = left_m is not None and left_m >= corridor_m + 0.5
    right_ok = right_m is not None and right_m >= corridor_m + 0.5

    if left_ok and not right_ok:
        advice, advice_str = "left", "more space to your left"
    elif right_ok and not left_ok:
        advice, advice_str = "right", "more space to your right"
    elif left_ok and right_ok:
        advice, advice_str = (("left", "more space to your left")
                              if left_m >= right_m
                              else ("right", "more space to your right"))
    else:
        advice, advice_str = "stop", "stop, blocked on both sides"

    return {"clear": False, "obstacle_m": corridor_m, "advice": advice,
            "advice_str": advice_str}


def should_announce_verdict(verdict):
    """
    Announce-gate for path verdicts: speak only when the (band, advice) state
    changes (e.g. clear -> blocked -> veer left), so we don't nag every frame.

    Returns the verdict if it should be spoken, else None.
    """
    global _last
    if verdict is None:
        return None
    band = ("clear" if verdict["clear"]
            else "near" if (verdict["obstacle_m"] or 99) < 1.5 else "mid")
    key = (band, verdict["advice"])
    if key != _last:
        _last = key
        return verdict
    return None


def reset_path_state():
    """Clear the announce-gate (call when the camera restarts)."""
    global _last
    _last = None

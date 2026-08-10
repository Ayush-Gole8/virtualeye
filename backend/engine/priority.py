"""
Priority scoring and selection engine — the core contribution.

This module implements cognitive-load-aware attention management: instead of
announcing every detected object every frame (which would overwhelm a blind user),
it scores each detection by closeness, position in the walking path, hazard class,
and motion state, then selects only the top-k most relevant objects.

Citation (cognitive load in assistive navigation):
Giudice, N. A., & Legge, G. E. (2008). Blind navigation and the role of technology.
In The Engineering Handbook of Smart Technology for Aging, Disability, and Independence.
(Wiley), 479-500.

Related work on priority-based narration for the visually impaired:
Yelamarthi, K., Haas, D., Nielsen, D., & Mothersell, S. (2010). RFID and GPS
integrated navigation system for the visually impaired. In 2010 53rd IEEE
International Midwest Symposium on Circuits and Systems (pp. 1149-1152). IEEE.
"""

# Hazard weight by COCO class: moving vehicles/bikes >> people >> static furniture >> small objects
HAZARD_WEIGHT = {
    # High hazard: moving vehicles and obstacles
    "person": 3,
    "bicycle": 4,
    "car": 5,
    "motorcycle": 5,
    "bus": 5,
    "truck": 5,
    "dog": 3,
    "cat": 2,
    # Medium hazard: large static obstacles
    "chair": 2,
    "couch": 2,
    "dining table": 2,
    "bench": 2,
    "door": 3,
    "staircase": 4,
    # Low hazard: small/passive objects
    "bottle": 1,
    "cup": 1,
    "laptop": 1,
    "tv": 1,
    "potted plant": 1,
    "book": 1,
}

# Motion bonus: approaching hazards deserve immediate attention
MOTION_BONUS = {
    "approaching": 3,
    "crossing": 2,
    "moving away": 0,
    "still": 0,
}


def compute_priority_score(det, frame_w, use_ttc=True):
    """
    Score a single detection. When use_ttc=True, approaching objects are ranked
    by time-to-collision instead of static distance — a person 3m away closing
    at 1 m/s (TTC=3s) outranks a chair 1.5m away that's stationary (TTC=inf).

    Scoring factors:
    1. TTC urgency (if approaching) OR closeness (if static/receding)
    2. In walking path (center third of frame = +3)
    3. Hazard class weight (1-5)
    4. Motion state bonus (0-3)

    Args:
        det: detection dict with 'distance', 'cx', 'class', 'motion', 'ttc'
        frame_w: frame width in pixels
        use_ttc: rank approaching objects by time-to-collision (default True)

    Returns:
        priority score (float, higher = more urgent)
    """
    dist = det.get("distance")
    if dist is None:
        dist = 10.0  # assume far if depth unavailable

    ttc = det.get("ttc")
    motion = det.get("motion", "still")

    # TTC urgency: if approaching and TTC available, invert it so lower TTC = higher urgency
    # Map TTC into a 0-10 scale: 1s -> 10, 5s -> 2, 10s+ -> 0
    if use_ttc and motion == "approaching" and ttc is not None and ttc < 999:
        urgency = max(0, 10.0 - ttc) if ttc < 10.0 else 0.0
    else:
        # Closeness fallback: linear ramp from 0 (>5m) to 5 (0m)
        urgency = max(0, 5.0 - dist) if dist < 5.0 else 0.0

    # In-path: is the object in the center third of the frame?
    cx = det.get("cx", frame_w / 2)
    left_edge = frame_w * 0.33
    right_edge = frame_w * 0.66
    in_path = 3.0 if left_edge <= cx <= right_edge else 0.0

    # Hazard class
    cls = det.get("class", "object")
    hazard = HAZARD_WEIGHT.get(cls, 1)

    # Motion bonus
    motion_bonus = MOTION_BONUS.get(motion, 0)

    # Final score (tunable weights)
    score = (urgency * 2.0) + in_path + hazard + motion_bonus
    return score


def prioritize(detections, frame_w, top_k=2, min_score=4.0, use_ttc=True):
    """
    Select the top-k highest-priority detections above a minimum score threshold.

    Args:
        detections: list of detection dicts
        frame_w: frame width
        top_k: max number of objects to announce
        min_score: minimum priority score to consider
        use_ttc: rank approaching objects by time-to-collision (default True)

    Returns:
        filtered and sorted list of top-k detections
    """
    scored = [(compute_priority_score(d, frame_w, use_ttc=use_ttc), d) for d in detections]
    scored = [(s, d) for s, d in scored if s >= min_score]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_k]]


def should_announce_now(det, track_id, last_announced):
    """
    Decide if a detection should be announced based on change since last time.

    Args:
        det: detection dict
        track_id: int
        last_announced: dict mapping track_id -> (dist_band, motion_state)

    Returns:
        True if something changed and we should announce
    """
    dist = det.get("distance")
    motion = det.get("motion", "still")

    # Distance bands: near (<1.5m), mid (1.5-3m), far (>3m)
    if dist is None:
        band = "far"
    elif dist < 1.5:
        band = "near"
    elif dist < 3.0:
        band = "mid"
    else:
        band = "far"

    key = (band, motion)
    prev = last_announced.get(track_id)

    if prev != key:
        last_announced[track_id] = key
        return True
    return False

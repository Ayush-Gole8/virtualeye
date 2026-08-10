"""
Motion state estimation from ByteTrack track history.

Uses per-track_id history of (timestamp, distance, horizontal position) to classify
each detected object's motion relative to the user as one of:
    "approaching", "moving away", "crossing", "still".

Citation (tracking):
Zhang, Y., Sun, P., Jiang, Y., et al. (2022). ByteTrack: Multi-Object Tracking by
Associating Every Detection Box. ECCV 2022. arXiv:2110.06864.

No model / training required — pure kinematic heuristic over Ultralytics track IDs.
"""

import time

# track_id -> (last_time, last_distance, last_cx)
_history = {}

# Tunable thresholds (metres/second and fraction-of-frame/second)
APPROACH_MPS = 0.30     # closing faster than this => "approaching"
RECEDE_MPS = 0.30       # opening faster than this => "moving away"
CROSS_FRAC = 0.15       # lateral speed > 15% frame width/s => "crossing"


def update_motion(detections, frame_w):
    """
    Annotate each detection dict with 'motion' key and closing-speed metrics.

    Args:
        detections: list of dicts, each with 'track_id', 'distance', 'cx'
        frame_w: frame width in pixels

    Returns:
        the same list, with 'motion', 'velocity_mps', and 'ttc' added
    """
    now = time.time()
    seen_ids = set()

    for det in detections:
        tid = det.get("track_id", -1)
        dist = det.get("distance")
        cx = det.get("cx")
        seen_ids.add(tid)

        state = "still"
        velocity_mps = 0.0  # depth velocity in m/s (negative = approaching)
        ttc = None          # time-to-collision in seconds (None = not approaching)

        if tid != -1 and tid in _history and dist is not None:
            t0, d0, x0 = _history[tid]
            dt = max(now - t0, 1e-3)

            # Depth velocity (negative = getting closer)
            d_vel = (dist - d0) / dt
            velocity_mps = d_vel
            # Lateral velocity in pixels/sec
            x_vel = (cx - x0) / dt

            if d_vel < -APPROACH_MPS:
                state = "approaching"
                # TTC: current distance / closing speed (use abs so it's positive seconds)
                ttc = dist / abs(d_vel) if abs(d_vel) > 1e-3 else 999.0
            elif d_vel > RECEDE_MPS:
                state = "moving away"
            elif abs(x_vel) > frame_w * CROSS_FRAC:
                state = "crossing"

        det["motion"] = state
        det["velocity_mps"] = velocity_mps
        det["ttc"] = ttc

        # Update history
        if tid != -1 and dist is not None:
            _history[tid] = (now, dist, cx)

    # Garbage-collect stale tracks (not seen in this frame and older than 5s)
    stale = [tid for tid, (t0, _, _) in _history.items()
             if tid not in seen_ids and now - t0 > 5.0]
    for tid in stale:
        del _history[tid]

    return detections


def reset_motion():
    """Clear all track history (call when camera restarts)."""
    _history.clear()

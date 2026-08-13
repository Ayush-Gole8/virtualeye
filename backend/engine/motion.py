"""
Motion state estimation from ByteTrack track history.
Each ByteTrack track maintains:
    (timestamp, distance_m, horizontal_center)
Motion is classified as:
    approaching
    moving away
    crossing
    still
TTC is computed only when the object is approaching:
    closing_speed = -(distance_t - distance_t-1) / dt
    TTC           = distance / closing_speed
No ML/training is required.
Reference:
    Zhang, Y., Sun, P., Jiang, Y., et al. (2022).
    ByteTrack: Multi-Object Tracking by Associating Every Detection Box.
    ECCV 2022. arXiv:2110.06864.
"""
from __future__ import annotations
import time
# ---------------------------------------------------------------------------
# Track history
# ---------------------------------------------------------------------------
# track_id -> (timestamp, distance_m, cx)
_history = {}
# ---------------------------------------------------------------------------
# Tunable motion thresholds
# ---------------------------------------------------------------------------
# Closing/opening speed in metres/second.
APPROACH_MPS = 0.30
RECEDE_MPS = 0.30
# Lateral movement threshold:
# > 15% frame width per second => crossing.
CROSS_FRAC = 0.15
# Ignore obviously invalid/unstable metric-depth values.
MIN_VALID_DISTANCE_M = 0.05
MAX_VALID_DISTANCE_M = 20.0
# Do not report TTC for extremely large values.
MAX_TTC_S = 30.0
# Remove tracks after this much time without observation.
STALE_TRACK_S = 5.0
def _valid_distance(distance):
    """Return True when distance is a usable metric-depth measurement."""
    if distance is None:
        return False
    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return False
    return (
        MIN_VALID_DISTANCE_M
        <= distance
        <= MAX_VALID_DISTANCE_M
    )

def update_motion(detections, frame_w):
    """
    Annotate detections with motion and TTC information.
    Expected input fields per detection:
        track_id
        distance
        cx
    Added fields:
        motion
            "approaching", "moving away", "crossing", "still"
        velocity_mps
            Signed depth velocity.
            Negative = getting closer.
        closing_speed_mps
            Positive = getting closer.
        lateral_velocity_px_s
            Signed horizontal velocity.
        ttc
            Time-to-collision in seconds, or None.
    Args:
        detections: list of detection dictionaries
        frame_w: frame width in pixels
    Returns:
        Same detection list, annotated in place.
    """
    now = time.monotonic()
    seen_ids = set()
    for det in detections:
        tid = det.get("track_id", -1)
        dist = det.get("distance")
        cx = det.get("cx")
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            tid = -1
        if cx is None:
            cx = frame_w / 2.0
        try:
            cx = float(cx)
        except (TypeError, ValueError):
            cx = frame_w / 2.0
        valid_distance = _valid_distance(dist)
        if valid_distance:
            dist = float(dist)
        if tid != -1:
            seen_ids.add(tid)
        # ------------------------------------------------------------------
        # Defaults
        # ------------------------------------------------------------------
        state = "still"
        # Signed depth velocity.
        # Negative = object is getting closer.
        velocity_mps = 0.0
        # Positive = closing.
        closing_speed_mps = 0.0
        lateral_velocity_px_s = 0.0
        ttc = None
        # ------------------------------------------------------------------
        # Temporal comparison
        # ------------------------------------------------------------------
        if (
            tid != -1
            and tid in _history
            and valid_distance
        ):
            t0, d0, x0 = _history[tid]
            dt = max(
                now - t0,
                1e-3,
            )
            # Depth velocity.
            d_vel = (
                dist - d0
            ) / dt
            velocity_mps = d_vel
            # Positive when the object approaches us.
            closing_speed_mps = max(
                0.0,
                -d_vel,
            )
            # Lateral velocity.
            lateral_velocity_px_s = (
                cx - x0
            ) / dt
            # --------------------------------------------------------------
            # Motion classification
            # --------------------------------------------------------------
            if d_vel < -APPROACH_MPS:
                state = "approaching"
                if closing_speed_mps > 1e-3:
                    candidate_ttc = (dist/ closing_speed_mps)
                    if (0.0< candidate_ttc<= MAX_TTC_S):
                        ttc = candidate_ttc
            elif d_vel > RECEDE_MPS:
                state = "moving away"
            elif (
                abs(lateral_velocity_px_s)
                > frame_w * CROSS_FRAC
            ):
                state = "crossing"
        # ------------------------------------------------------------------
        # Write results
        # ------------------------------------------------------------------

        det["motion"] = state
        det["velocity_mps"] = velocity_mps
        det["closing_speed_mps"] = closing_speed_mps
        det["lateral_velocity_px_s"] = (
            lateral_velocity_px_s
        )
        det["ttc"] = ttc

        # ------------------------------------------------------------------
        # Update track history
        # ------------------------------------------------------------------

        if (
            tid != -1
            and valid_distance
        ):
            _history[tid] = (
                now,
                dist,
                cx,
            )

    # ----------------------------------------------------------------------
    # Garbage collection
    # ----------------------------------------------------------------------

    stale = [
        tid
        for tid, (
            t0,
            _,
            _,
        ) in _history.items()
        if (
            tid not in seen_ids
            and now - t0 > STALE_TRACK_S
        )
    ]

    for tid in stale:
        del _history[tid]

    return detections


def reset_motion():
    """
    Clear all track history.

    Call when:
        - camera restarts
        - video source changes
        - tracking session resets
    """
    _history.clear()
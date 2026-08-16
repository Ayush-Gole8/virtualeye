"""
Priority scoring and selection engine.

This module performs cognitive-load-aware attention management.

Priority is determined by:

    1. TTC urgency for approaching objects
    2. Dynamic-threat class
    3. Position in the walking corridor
    4. Static proximity
    5. General hazard class
    6. Motion state

The TTC component is deliberately represented as interpretable bands:

    high agility:
        critical <= 0
        high      < 3 s
        medium    < 6 s
        low       >= 6 s

    low agility:
        critical <= 0
        high      < 4 s
        medium    < 8 s
        low       >= 8 s

A small temporal debounce prevents one noisy TTC observation from
immediately producing a high-priority warning.

References:
    Pundlik, S., Baliutaviciute, V., Moharrer, M., Bowers, A. R.,
    Luo, G. (2021). Home-Use Evaluation of a Wearable Collision Warning
    Device for Individuals With Severe Vision Impairments.
    JAMA Ophthalmology, 139(9), 998-1005.

    Zhang, Y., Sun, P., Jiang, Y., et al. (2022). ByteTrack.
"""

from __future__ import annotations

from collections import defaultdict, deque
import time


# ---------------------------------------------------------------------------
# Hazard class weights
# ---------------------------------------------------------------------------

HAZARD_WEIGHT = {
    # Dynamic/high-consequence classes
    "person": 3,
    "bicycle": 4,
    "car": 5,
    "motorcycle": 5,
    "bus": 5,
    "truck": 5,
    "dog": 3,
    "cat": 2,

    # Large static obstacles
    "chair": 2,
    "couch": 2,
    "dining table": 2,
    "bench": 2,
    "door": 3,
    "staircase": 4,

    # Small/passive objects
    "bottle": 1,
    "cup": 1,
    "laptop": 1,
    "tv": 1,
    "potted plant": 1,
    "book": 1,
}


VEHICLE_CLASSES = {
    "car",
    "bus",
    "truck",
    "motorcycle",
    "bicycle",
}


DYNAMIC_CLASSES = {
    "person",
    *VEHICLE_CLASSES,
}


ANIMATED_HAZARD_CLASSES = {
    *DYNAMIC_CLASSES,
    "dog",
    "cat",
}


STATIC_OBSTACLE_CLASSES = {
    "person",
    "dog",
    "cat",
    "chair",
    "couch",
    "dining table",
    "bench",
    "door",
    "staircase",
    "bed",
    "toilet",
    "potted plant",
    "backpack",
    "handbag",
    "suitcase",
}


TRIP_HAZARD_CLASSES = {
    "bottle",
    "cup",
    "book",
    "sports ball",
    "skateboard",
    "backpack",
    "handbag",
    "suitcase",
}


MOTION_BONUS = {
    "approaching": 3,
    "crossing": 2,
    "moving away": 0,
    "still": 0,
}


# ---------------------------------------------------------------------------
# TTC policy
# ---------------------------------------------------------------------------

TTC_HIGH_S = 3.0
TTC_MEDIUM_S = 6.0

LOW_AGILITY_TTC_HIGH_S = 4.0
LOW_AGILITY_TTC_MEDIUM_S = 8.0


# ---------------------------------------------------------------------------
# Temporal debounce
# ---------------------------------------------------------------------------

TTC_DEBOUNCE_FRAMES = 3
TTC_HISTORY_SIZE = 6


STATIC_RISK_DISTANCE_M = 1.75
TRIP_RISK_DISTANCE_M = 1.0
CROSSING_RISK_DISTANCE_M = 4.0
VEHICLE_RISK_DISTANCE_M = 3.0
OBJECT_REMINDER_S = 8.0
OBJECT_STATE_CHANGE_COOLDOWN_S = 4.0
SEMANTIC_DEDUP_S = OBJECT_REMINDER_S
HAZARD_REMINDER_S = 8.0


class TTCDebouncer:
    """
    Require a decreasing TTC trend over N observations before confirming
    a high-risk TTC event.

    State is maintained per ByteTrack track_id.
    """

    def __init__(
        self,
        required_frames=TTC_DEBOUNCE_FRAMES,
        history_size=TTC_HISTORY_SIZE,
    ):
        self.required_frames = max(
            2,
            int(required_frames),
        )

        self.history_size = max(
            self.required_frames,
            int(history_size),
        )

        self._history = defaultdict(
            lambda: deque(
                maxlen=self.history_size
            )
        )

    def update(
        self,
        track_id,
        ttc,
        high_threshold,
    ):
        """
        Add one TTC observation.

        Returns:
            {
                "confirmed": bool,
                "decreasing": bool,
                "history": list[float]
            }
        """
        key = track_id

        if (
            key is None
            or key == -1
        ):
            return {
                "confirmed": False,
                "decreasing": False,
                "history": [],
            }

        history = self._history[key]

        if ttc is None:
            history.clear()

            return {
                "confirmed": False,
                "decreasing": False,
                "history": [],
            }

        try:
            ttc = float(ttc)
        except (TypeError, ValueError):
            history.clear()

            return {
                "confirmed": False,
                "decreasing": False,
                "history": [],
            }

        if ttc <= 0.0:
            history.append(ttc)

            # Collision/imminent condition should not wait for debounce.
            return {
                "confirmed": True,
                "decreasing": True,
                "history": list(history),
            }

        history.append(ttc)

        if len(history) < self.required_frames:
            return {
                "confirmed": False,
                "decreasing": False,
                "history": list(history),
            }

        recent = list(
            history
        )[-self.required_frames:]

        decreasing = all(
            recent[i] > recent[i + 1]
            for i in range(
                len(recent) - 1
            )
        )

        confirmed = (
            decreasing
            and recent[-1] < high_threshold
        )

        return {
            "confirmed": confirmed,
            "decreasing": decreasing,
            "history": list(history),
        }

    def clear(self, track_id):
        """Clear state for one track."""
        self._history.pop(
            track_id,
            None,
        )

    def reset(self):
        """Clear all debounce state."""
        self._history.clear()


_ttc_debouncer = TTCDebouncer()


# ---------------------------------------------------------------------------
# TTC urgency
# ---------------------------------------------------------------------------

def urgency_band(
    ttc,
    agility="high",
):
    """
    Convert TTC into an interpretable urgency band.

    Args:
        ttc: seconds, or None
        agility:
            "high" -> earlier threshold at 3 s
            "low"  -> earlier threshold at 4 s

    Returns:
        "critical", "high", "medium", "low", or "none"
    """
    if ttc is None:
        return "none"

    try:
        ttc = float(ttc)
    except (TypeError, ValueError):
        return "none"

    if ttc <= 0.0:
        return "critical"

    agility = (
        str(agility)
        .strip()
        .lower()
    )

    if agility == "low":
        high_threshold = (
            LOW_AGILITY_TTC_HIGH_S
        )
        medium_threshold = (
            LOW_AGILITY_TTC_MEDIUM_S
        )
    else:
        high_threshold = (
            TTC_HIGH_S
        )
        medium_threshold = (
            TTC_MEDIUM_S
        )

    if ttc < high_threshold:
        return "high"

    if ttc < medium_threshold:
        return "medium"

    return "low"


# ---------------------------------------------------------------------------
# Dynamic-threat weighting
# ---------------------------------------------------------------------------

def dynamic_threat_weight(det):
    """
    Return a secondary priority weight for a moving object.

    Vehicles receive the highest dynamic-threat weight.
    People receive the next-highest weight.
    """

    cls = str(
        det.get(
            "class",
            "",
        )
    ).lower()

    motion = str(
        det.get(
            "motion",
            "still",
        )
    ).lower()

    if motion not in {
        "approaching",
        "crossing",
    }:
        return 0.0

    if cls in VEHICLE_CLASSES:
        return 10.0

    if cls == "person":
        return 8.0

    if cls in DYNAMIC_CLASSES:
        return 5.0

    return 2.0


def _valid_distance(det):
    distance = det.get("distance")
    if distance is None:
        return None

    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return None

    if distance < 0.0:
        return None

    return distance


def _is_in_path(det, frame_w):
    try:
        center_x = float(det.get("cx", frame_w / 2.0))
    except (TypeError, ValueError):
        center_x = frame_w / 2.0

    return frame_w * 0.33 <= center_x <= frame_w * 0.66


def _is_low_in_frame(det, frame_h):
    if frame_h is None:
        return True

    bbox = det.get("bbox")
    if not bbox or len(bbox) != 4:
        return True

    try:
        bottom = float(bbox[3])
        frame_h = float(frame_h)
    except (TypeError, ValueError):
        return True

    if frame_h <= 0.0:
        return True

    return bottom >= frame_h * 0.55


def is_actionable_risk(det, frame_w, frame_h=None):
    """Return True only for an object that warrants automatic speech."""
    cls = str(det.get("class", "")).strip().lower()
    motion = str(det.get("motion", "still")).strip().lower()
    urgency = str(det.get("urgency_band", "none")).strip().lower()
    distance = _valid_distance(det)
    in_path = _is_in_path(det, frame_w)

    if motion == "approaching" and cls in ANIMATED_HAZARD_CLASSES:
        if urgency in {"critical", "high"}:
            return bool(det.get("ttc_high_confirmed", False))
        if urgency == "medium":
            return True

    if (
        motion == "crossing"
        and cls in ANIMATED_HAZARD_CLASSES
        and distance is not None
        and distance <= CROSSING_RISK_DISTANCE_M
    ):
        return True

    if (
        cls in VEHICLE_CLASSES
        and in_path
        and distance is not None
        and distance <= VEHICLE_RISK_DISTANCE_M
    ):
        return True

    if (
        cls in STATIC_OBSTACLE_CLASSES
        and in_path
        and distance is not None
        and distance <= STATIC_RISK_DISTANCE_M
    ):
        return True

    if (
        cls in TRIP_HAZARD_CLASSES
        and in_path
        and distance is not None
        and distance <= TRIP_RISK_DISTANCE_M
        and _is_low_in_frame(det, frame_h)
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Priority score
# ---------------------------------------------------------------------------

def compute_priority_score(
    det,
    frame_w,
    use_ttc=True,
    agility="high",
):
    """
    Compute a transparent priority score.

    Score components:

        TTC urgency:
            critical = 20
            high     = 15
            medium   = 8
            low      = 2

        Dynamic threat:
            vehicle  = +10
            person   = +8

        Path:
            center corridor = +5

        Static proximity:
            up to +5

        Hazard class:
            1-5

        Motion:
            0-3

    TTC dominates proximity when an object is actually approaching.
    """

    dist = det.get(
        "distance"
    )

    if dist is None:
        dist = 10.0
    else:
        try:
            dist = max(
                0.0,
                float(dist),
            )
        except (
            TypeError,
            ValueError,
        ):
            dist = 10.0

    ttc = det.get(
        "ttc"
    )

    motion = det.get(
        "motion",
        "still",
    )

    band = urgency_band(
        ttc,
        agility=agility,
    )

    # Store the interpretable result directly on the detection.
    det["urgency_band"] = band

    # ----------------------------------------------------------------------
    # TTC urgency
    # ----------------------------------------------------------------------

    if (
        use_ttc
        and motion == "approaching"
        and ttc is not None
    ):
        urgency = {
            "critical": 20.0,
            "high": 15.0,
            "medium": 8.0,
            "low": 2.0,
            "none": 0.0,
        }.get(
            band,
            0.0,
        )
    else:
        # Static/receding fallback.
        # 5 m -> 0
        # 0 m -> 5
        urgency = max(
            0.0,
            5.0 - dist,
        )

    # ----------------------------------------------------------------------
    # In-path bonus
    # ----------------------------------------------------------------------

    cx = det.get(
        "cx",
        frame_w / 2,
    )

    try:
        cx = float(cx)
    except (
        TypeError,
        ValueError,
    ):
        cx = frame_w / 2

    in_path = (
        5.0
        if (
            frame_w * 0.33
            <= cx
            <= frame_w * 0.66
        )
        else 0.0
    )

    # ----------------------------------------------------------------------
    # Hazard class
    # ----------------------------------------------------------------------

    cls = det.get(
        "class",
        "object",
    )

    hazard = HAZARD_WEIGHT.get(
        cls,
        1,
    )

    # ----------------------------------------------------------------------
    # Motion
    # ----------------------------------------------------------------------

    motion_bonus = MOTION_BONUS.get(
        motion,
        0,
    )

    # ----------------------------------------------------------------------
    # Dynamic class
    # ----------------------------------------------------------------------

    dynamic_bonus = (
        dynamic_threat_weight(
            det
        )
    )

    # ----------------------------------------------------------------------
    # Final score
    # ----------------------------------------------------------------------

    score = (
        urgency
        + dynamic_bonus
        + in_path
        + hazard
        + motion_bonus
    )

    det["priority"] = float(
        score
    )

    return float(score)


# ---------------------------------------------------------------------------
# Temporal TTC annotation
# ---------------------------------------------------------------------------

def update_ttc_state(
    det,
    agility="high",
):
    """
    Add debounce-related TTC fields to one detection.

    This must be called once per frame for each tracked detection.
    """

    tid = det.get(
        "track_id",
        -1,
    )

    ttc = det.get(
        "ttc"
    )

    high_threshold = (
        LOW_AGILITY_TTC_HIGH_S
        if str(agility).lower() == "low"
        else TTC_HIGH_S
    )

    state = _ttc_debouncer.update(
        tid,
        ttc,
        high_threshold,
    )

    det["ttc_decreasing"] = (
        state["decreasing"]
    )

    det["ttc_high_confirmed"] = (
        state["confirmed"]
    )

    return det


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def prioritize(
    detections,
    frame_w,
    frame_h=None,
    top_k=2,
    min_score=4.0,
    use_ttc=True,
    agility="high",
    actionable_only=True,
):
    """
    Select the most relevant detections.

    TTC state is updated before scoring.

    For high-risk TTC alerts, confirmation is required before the
    detection receives its full high-risk score.
    """

    scored = []

    for det in detections:
        update_ttc_state(
            det,
            agility=agility,
        )

        score = compute_priority_score(
            det,
            frame_w,
            use_ttc=use_ttc,
            agility=agility,
        )

        # --------------------------------------------------------------
        # Debounce high TTC.
        #
        # A high TTC state should not receive its complete priority
        # until the decreasing-TTC trend has been confirmed.
        # --------------------------------------------------------------

        if det.get(
            "urgency_band"
        ) == "high":
            if not det.get(
                "ttc_high_confirmed",
                False,
            ):
                # Keep it visible to the ranking engine,
                # but suppress the high-risk component.
                score -= 15.0

        det["priority"] = max(
            0.0,
            float(score),
        )

        if actionable_only and not is_actionable_risk(
            det,
            frame_w,
            frame_h=frame_h,
        ):
            continue

        if det["priority"] >= min_score:
            scored.append(
                (
                    det["priority"],
                    det,
                )
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        det
        for _, det in scored[:top_k]
    ]


# ---------------------------------------------------------------------------
# Existing announcement gate
# ---------------------------------------------------------------------------

def should_announce_now(
    det,
    track_id,
    last_announced,
    now=None,
    reminder_s=OBJECT_REMINDER_S,
    state_change_cooldown_s=OBJECT_STATE_CHANGE_COOLDOWN_S,
    semantic_dedup_s=SEMANTIC_DEDUP_S,
):
    """
    Decide whether the semantic state of a tracked detection has changed.

    Existing distance/motion behavior is retained.

    High TTC additionally requires temporal confirmation.
    """

    dist = det.get(
        "distance"
    )

    motion = det.get(
        "motion",
        "still",
    )

    band = det.get("urgency_band") or urgency_band(det.get("ttc"))

    # Distance bands.
    if dist is None:
        dist_band = "far"

    else:
        try:
            dist = float(dist)

            if dist < 1.5:
                dist_band = "near"
            elif dist < 3.0:
                dist_band = "mid"
            else:
                dist_band = "far"

        except (
            TypeError,
            ValueError,
        ):
            dist_band = "far"

    # High-risk TTC cannot announce before debounce.
    if band in {
        "critical",
        "high",
    }:
        if not det.get(
            "ttc_high_confirmed",
            False,
        ):
            return False

    key = (
        dist_band,
        motion,
        band,
    )

    if now is None:
        now = time.monotonic()

    previous = last_announced.get(track_id)
    if isinstance(previous, dict):
        previous_key = previous.get("key")
        previous_at = float(previous.get("at", 0.0))
    else:
        previous_key = previous
        previous_at = 0.0

    semantic_key = (
        "semantic",
        str(det.get("class", "object")).lower(),
        det.get("side", "center"),
        *key,
    )
    semantic_previous = last_announced.get(semantic_key)
    semantic_at = (
        float(semantic_previous.get("at", 0.0))
        if isinstance(semantic_previous, dict)
        else 0.0
    )

    state_changed = previous_key != key
    reminder_due = now - previous_at >= reminder_s
    semantic_recent = (
        isinstance(semantic_previous, dict)
        and now - semantic_at < semantic_dedup_s
    )

    if previous_key is not None and state_changed:
        previous_distance, previous_motion, previous_band = previous_key
        distance_rank = {"far": 0, "mid": 1, "near": 2}
        motion_rank = {
            "moving away": 0,
            "still": 0,
            "crossing": 1,
            "approaching": 2,
        }
        urgency_rank = {
            "none": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }
        escalated = (
            distance_rank.get(dist_band, 0) > distance_rank.get(previous_distance, 0)
            or motion_rank.get(motion, 0) > motion_rank.get(previous_motion, 0)
            or urgency_rank.get(band, 0) > urgency_rank.get(previous_band, 0)
        )
        if not escalated and now - previous_at < state_change_cooldown_s:
            return False

    if semantic_recent and state_changed:
        return False

    if not state_changed and not reminder_due:
        return False

    record = {"key": key, "at": now}
    last_announced[track_id] = record
    last_announced[semantic_key] = record
    return True


def should_announce_hazard_now(
    hazard_type,
    result,
    last_announced,
    now=None,
    reminder_s=HAZARD_REMINDER_S,
):
    """Gate repeated structural warnings while allowing periodic reminders."""
    cache_key = ("hazard", str(hazard_type).lower())

    if not result or not result.get("detected", False):
        return False

    if now is None:
        now = time.monotonic()

    distance = result.get("distance_m")
    try:
        distance = float(distance)
    except (TypeError, ValueError):
        distance = None

    if distance is None:
        distance_band = "unknown"
    elif distance < 1.0:
        distance_band = "immediate"
    elif distance < 2.0:
        distance_band = "near"
    else:
        distance_band = "far"

    state = (
        distance_band,
        bool(result.get("confirmed", result.get("detected", False))),
        result.get("advice"),
    )
    previous = last_announced.get(cache_key)

    if isinstance(previous, dict):
        previous_state = previous.get("key")
        previous_at = float(previous.get("at", 0.0))
    else:
        previous_state = None
        previous_at = 0.0

    if previous_state is not None and now - previous_at < reminder_s:
        distance_rank = {"unknown": 0, "far": 1, "near": 2, "immediate": 3}
        previous_band = previous_state[0]
        if distance_rank.get(distance_band, 0) <= distance_rank.get(previous_band, 0):
            return False

    last_announced[cache_key] = {"key": state, "at": now}
    return True


def reset_priority_state():
    """Clear TTC debounce state."""
    _ttc_debouncer.reset()

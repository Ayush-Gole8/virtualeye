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
    top_k=2,
    min_score=4.0,
    use_ttc=True,
    agility="high",
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

    band = urgency_band(
        det.get(
            "ttc"
        )
    )

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

    previous = last_announced.get(
        track_id
    )

    if previous != key:
        last_announced[
            track_id
        ] = key

        return True

    return False


def reset_priority_state():
    """Clear TTC debounce state."""
    _ttc_debouncer.reset()
"""
Depth-based navigation and safety analysis.

This module provides three independent geometric analyses:

1. analyze_path()
       Ground-level forward walkability.

2. analyze_overhead()
       Upper-central head/upper-body obstacle detection.

3. detect_dropoff()
       Downward discontinuity detection for stairs, curbs and drop-offs.

All operations are NumPy-only and reuse the metric depth map already produced
by the main vision pipeline.

Important:
    These are conservative engineering heuristics. They are not certified
    safety systems and their thresholds must be validated on recorded clips.
"""

from __future__ import annotations

import numpy as np


# ============================================================================
# Existing ground-path detector
# ============================================================================

CORRIDOR_FRAC = 0.40

BLOCKED_M = 2.0

CAUTION_M = 3.0

ROBUST_Q = 5.0

FLOOR_BAND = 0.25

_last = None


# ============================================================================
# New overhead detector
# ============================================================================

HEAD_TOP_FRAC = 0.35

HEAD_CORRIDOR_FRAC = 0.50

HEAD_MAX_DISTANCE_M = 1.50

HEAD_ROBUST_Q = 10.0

HEAD_MIN_VALID_FRACTION = 0.15

HEAD_MIN_NEAR_FRACTION = 0.02


# ============================================================================
# New drop-off detector
# ============================================================================

DROPOFF_START_FRAC = 0.55

DROPOFF_END_FRAC = 0.95

DROPOFF_CORRIDOR_FRAC = 0.50

# A drop-off makes the FARTHER (upper) band sit abnormally far beyond the
# NEARER (lower) band. These gate the size of that occlusion gap.
DROPOFF_JUMP_M = 0.40

DROPOFF_RATIO = 1.25

# The gap must also beat ordinary floor perspective: it must exceed
# DROPOFF_GRAD_MULT * (local smooth gradient * comparison window).
DROPOFF_GRAD_MULT = 2.5

DROPOFF_SMOOTH_WINDOW = 5

DROPOFF_COMPARISON_WINDOW = 5

DROPOFF_MIN_VALID_FRACTION = 0.20

# Anchor on the NEAR (edge) side. Only warn about drop-offs whose edge is
# within a walking-relevant range; a drop-off far away is not actionable yet
# and widening this invites false positives from distant floor perspective.
DROPOFF_MIN_SURFACE_M = 0.30

DROPOFF_MAX_SURFACE_M = 6.0


# Temporal confirmation for drop-off candidates.
DROPOFF_CONFIRM_FRAMES = 2

_dropoff_streak = 0


# ============================================================================
# Shared helpers
# ============================================================================
# ============================================================================
# Shared step-clustering helper (used by staircase detection AND the
# vehicle-geometry veto below)
# ============================================================================

def _cluster_step_transitions(smooth, jump_min_m, jump_max_m, cluster_gap=2):
    """
    Find clusters of consecutive rows whose row-to-row depth change falls in
    [jump_min_m, jump_max_m] -- i.e. plausible individual stair-riser
    transitions (small and repeated, as opposed to one big drop-off jump).

    Returns a list of cluster center row-indices, one per transition.
    """
    diffs = np.diff(smooth)
    idx = np.where(
        (np.abs(diffs) >= jump_min_m) & (np.abs(diffs) <= jump_max_m)
    )[0]

    if idx.size == 0:
        return []

    clusters = []
    current = [int(idx[0])]
    for i in idx[1:]:
        if i - current[-1] <= cluster_gap:
            current.append(int(i))
        else:
            clusters.append(current)
            current = [int(i)]
    clusters.append(current)

    return [int(np.mean(c)) for c in clusters]


# ============================================================================
# Staircase detector
# ============================================================================

STAIR_START_FRAC = 0.40
STAIR_END_FRAC = 0.95
STAIR_CORRIDOR_FRAC = 0.45
STAIR_MIN_VALID_FRACTION = 0.20
STAIR_MIN_STEPS = 3
STAIR_STEP_JUMP_MIN_M = 0.04
STAIR_STEP_JUMP_MAX_M = 0.30
STAIR_SPACING_CV_MAX = 0.6
STAIR_SMOOTH_WINDOW = 3
STAIR_CONFIRM_FRAMES = 2

_staircase_streak = 0


def detect_staircase(
    depth_map,
    *,
    start_fraction=STAIR_START_FRAC,
    end_fraction=STAIR_END_FRAC,
    corridor_fraction=STAIR_CORRIDOR_FRAC,
    min_steps=STAIR_MIN_STEPS,
    step_jump_min_m=STAIR_STEP_JUMP_MIN_M,
    step_jump_max_m=STAIR_STEP_JUMP_MAX_M,
):
    """
    Detect a repeating staircase pattern (ascending or descending) in the
    walking corridor.

    Geometric signature (distinct from both floor perspective and a single
    drop-off): a staircase produces SEVERAL roughly evenly-spaced small
    depth jumps down the image -- one per riser -- of similar magnitude.
    detect_dropoff() looks for exactly ONE large jump; this looks for
    several SMALL, PERIODIC ones instead.

    Returns:
        {detected, candidate, confirmed, distance_m,
         step_count, spacing_cv, confidence, roi}
    """
    global _staircase_streak

    depth_map = np.asarray(depth_map, dtype=np.float32)
    if depth_map.ndim != 2:
        raise ValueError("depth_map must be 2-D")

    h, w = depth_map.shape

    y0 = max(0, int(round(h * start_fraction)))
    y1 = min(h, int(round(h * end_fraction)))
    corridor_w = max(1, int(round(w * corridor_fraction)))
    x0 = (w - corridor_w) // 2
    x1 = x0 + corridor_w

    roi = depth_map[y0:y1, x0:x1]

    row_depth = _row_depth_profile(roi, min_valid_fraction=STAIR_MIN_VALID_FRACTION)
    profile = _fill_nan_profile(row_depth)

    def _empty(step_count=0, reason=None):
        out = {
            "detected": False, "candidate": False, "confirmed": False,
            "distance_m": None, "step_count": step_count, "confidence": 0.0,
        }
        if reason:
            out["reason"] = reason
        return out

    if profile is None or len(profile) < (2 * min_steps + 4):
        _staircase_streak = 0
        return _empty(reason="insufficient_valid_depth")

    smooth = _smooth_profile(profile, window=STAIR_SMOOTH_WINDOW)

    centers = _cluster_step_transitions(smooth, step_jump_min_m, step_jump_max_m)
    step_count = len(centers)

    if step_count < min_steps:
        _staircase_streak = 0
        return _empty(step_count=step_count, reason="too_few_steps")

    spacings = np.diff(centers)
    if len(spacings) == 0 or np.median(spacings) <= 0:
        _staircase_streak = 0
        return _empty(step_count=step_count, reason="no_spacing")

    spacing_cv = float(np.std(spacings) / (np.median(spacings) + 1e-6))

    if spacing_cv > STAIR_SPACING_CV_MAX:
        _staircase_streak = 0
        return _empty(step_count=step_count, reason="not_periodic")

    _staircase_streak += 1
    confirmed = _staircase_streak >= STAIR_CONFIRM_FRAMES

    nearest_idx = min(centers[-1] + 1, len(smooth) - 1)
    distance_m = float(smooth[nearest_idx])

    confidence = float(np.clip(
        (step_count / (min_steps + 2)) * (1.0 - spacing_cv), 0.0, 1.0,
    ))

    return {
        "detected": bool(confirmed),
        "candidate": True,
        "confirmed": bool(confirmed),
        "distance_m": distance_m,
        "step_count": int(step_count),
        "spacing_cv": spacing_cv,
        "confidence": confidence,
        "roi": {"x0": x0, "x1": x1, "y0": y0, "y1": y1},
    }


# ============================================================================
# Vehicle-class geometric veto (Layer 1 — fires before detect_staircase even
# gets a chance to run, directly in the detection loop)
# ============================================================================

VEHICLE_STEP_JUMP_MIN_M = 0.03
VEHICLE_STEP_JUMP_MAX_M = 0.35
VEHICLE_MIN_STEPS_TO_REJECT = 2
VEHICLE_INTERIOR_PAD = 0.15


def plausible_vehicle_geometry(depth_map, bbox):
    """
    Sanity-check a YOLO 'vehicle-class' box (car/bus/truck/motorcycle/
    bicycle) against its own depth profile.

    YOLO's COCO-80 classes have no 'stairs' label, so a gray staircase
    (uniform colour, boxy silhouette, repeated horizontal edges) sometimes
    gets misclassified as 'car'. A real vehicle presents one roughly
    continuous depth surface across its box. A staircase shot head-on
    shows the same repeating small-step pattern detect_staircase() looks
    for, just confined to the box. If we find that pattern inside a
    'vehicle' box, the label is almost certainly wrong.

    Returns:
        True  -> geometry is consistent with a real vehicle (keep it)
        False -> looks like steps, not a vehicle (drop the detection)
    """
    depth_map = np.asarray(depth_map, dtype=np.float32)
    h, w = depth_map.shape

    x1, y1, x2, y2 = map(int, bbox)
    bw, bh = x2 - x1, y2 - y1
    if bw <= 4 or bh <= 4:
        return True  # too small to judge; don't veto on weak data

    pad_x, pad_y = int(bw * VEHICLE_INTERIOR_PAD), int(bh * VEHICLE_INTERIOR_PAD)
    ix0, ix1 = max(0, x1 + pad_x), min(w, x2 - pad_x)
    iy0, iy1 = max(0, y1 + pad_y), min(h, y2 - pad_y)

    if ix1 <= ix0 or iy1 <= iy0:
        return True

    roi = depth_map[iy0:iy1, ix0:ix1]
    row_depth = _row_depth_profile(roi, min_valid_fraction=0.25)
    profile = _fill_nan_profile(row_depth)

    if profile is None or len(profile) < 8:
        return True  # not enough signal to veto; benefit of the doubt

    smooth = _smooth_profile(profile, window=3)
    centers = _cluster_step_transitions(
        smooth, VEHICLE_STEP_JUMP_MIN_M, VEHICLE_STEP_JUMP_MAX_M
    )

    return len(centers) < VEHICLE_MIN_STEPS_TO_REJECT

def _valid_depths(depth_map):
    """
    Boolean mask for usable metric-depth values.

    0, NaN and Inf are rejected.
    """
    depth_map = np.asarray(
        depth_map,
        dtype=np.float32,
    )

    return (
        np.isfinite(depth_map)
        & (depth_map > 0.02)
    )


def _nearest_in_zone(
    depth_map,
    mask,
    x0,
    x1,
    robust_q=ROBUST_Q,
):
    """
    Return a robust nearest-depth estimate in an image region.

    Only rows above FLOOR_BAND are used for the regular path detector.
    """
    rows = int(
        depth_map.shape[0]
        * (1.0 - FLOOR_BAND)
    )

    zone = (
        depth_map[
            :rows,
            x0:x1
        ][
            mask[
                :rows,
                x0:x1
            ]
        ]
    )

    if zone.size == 0:
        return None

    return float(
        np.percentile(
            zone,
            robust_q,
        )
    )


# ============================================================================
# Ground-path analysis
# ============================================================================

def analyze_path(
    depth_map,
    frame_w,
    frame_h,
):
    """
    Analyse forward walkability.

    Returns:
        {
            clear: bool,
            obstacle_m: float | None,
            advice: "clear" | "left" | "right" | "stop",
            advice_str: str
        }
    """
    del frame_h

    depth_map = np.asarray(
        depth_map,
        dtype=np.float32,
    )

    mask = _valid_depths(
        depth_map
    )

    cx0 = int(
        frame_w
        * (
            0.5
            - CORRIDOR_FRAC / 2
        )
    )

    cx1 = int(
        frame_w
        * (
            0.5
            + CORRIDOR_FRAC / 2
        )
    )

    corridor_m = _nearest_in_zone(
        depth_map,
        mask,
        cx0,
        cx1,
    )

    left_m = _nearest_in_zone(
        depth_map,
        mask,
        0,
        int(
            frame_w * 0.33
        ),
    )

    right_m = _nearest_in_zone(
        depth_map,
        mask,
        int(
            frame_w * 0.66
        ),
        frame_w,
    )

    if corridor_m is None:
        return {
            "clear": False,
            "obstacle_m": None,
            "advice": "stop",
            "advice_str": (
                "cannot see the path ahead"
            ),
        }

    if corridor_m >= BLOCKED_M:
        return {
            "clear": True,
            "obstacle_m": corridor_m,
            "advice": "clear",
            "advice_str": "path clear",
        }

    left_ok = (
        left_m is not None
        and left_m >= corridor_m + 0.5
    )

    right_ok = (
        right_m is not None
        and right_m >= corridor_m + 0.5
    )

    if left_ok and not right_ok:
        advice = "left"
        advice_str = (
            "more space to your left"
        )

    elif right_ok and not left_ok:
        advice = "right"
        advice_str = (
            "more space to your right"
        )

    elif left_ok and right_ok:
        if left_m >= right_m:
            advice = "left"
            advice_str = (
                "more space to your left"
            )
        else:
            advice = "right"
            advice_str = (
                "more space to your right"
            )

    else:
        advice = "stop"
        advice_str = (
            "stop, blocked on both sides"
        )

    return {
        "clear": False,
        "obstacle_m": corridor_m,
        "advice": advice,
        "advice_str": advice_str,
    }


# ============================================================================
# Path announcement gate
# ============================================================================

def should_announce_verdict(
    verdict,
):
    """
    Announce path changes only when the state changes.

    This avoids repeating the same path message on every frame.
    """
    global _last

    if verdict is None:
        return None

    obstacle_m = verdict.get(
        "obstacle_m"
    )

    if verdict.get(
        "clear",
        False,
    ):
        band = "clear"

    elif (
        obstacle_m is not None
        and obstacle_m < 1.5
    ):
        band = "near"

    else:
        band = "mid"

    key = (
        band,
        verdict.get(
            "advice",
            "unknown",
        ),
    )

    if key != _last:
        _last = key
        return verdict

    return None


# ============================================================================
# Head-height / upper-body hazard
# ============================================================================

def analyze_overhead(
    depth_map,
    *,
    top_fraction=HEAD_TOP_FRAC,
    corridor_fraction=HEAD_CORRIDOR_FRAC,
    max_distance_m=HEAD_MAX_DISTANCE_M,
    percentile=HEAD_ROBUST_Q,
    min_valid_fraction=HEAD_MIN_VALID_FRACTION,
    min_near_fraction=HEAD_MIN_NEAR_FRACTION,
):
    """
    Detect a robust near-depth region in the upper-central image.

    ROI:
        top ~35% of image
        central ~50% of width

    Detection requires:

        valid_fraction >= min_valid_fraction
        robust_depth <= max_distance_m
        near_fraction >= min_near_fraction

    This intentionally does not classify the object.
    The detector knows only that a nearby upper-region surface exists.
    """

    depth_map = np.asarray(
        depth_map,
        dtype=np.float32,
    )

    if depth_map.ndim != 2:
        raise ValueError(
            "depth_map must be 2-D"
        )

    h, w = depth_map.shape

    roi_h = max(
        1,
        int(
            round(
                h * top_fraction
            )
        ),
    )

    roi_w = max(
        1,
        int(
            round(
                w * corridor_fraction
            )
        ),
    )

    x0 = (
        w - roi_w
    ) // 2

    x1 = x0 + roi_w

    roi = depth_map[
        :roi_h,
        x0:x1
    ]

    valid = (
        np.isfinite(roi)
        & (roi > 0.02)
    )

    total = roi.size

    valid_count = int(
        valid.sum()
    )

    valid_fraction = (
        valid_count / total
        if total
        else 0.0
    )

    if valid_count == 0:
        return {
            "detected": False,
            "distance_m": None,
            "confidence": 0.0,
            "valid_fraction": valid_fraction,
            "near_fraction": 0.0,
        }

    values = roi[valid]

    robust_distance = float(
        np.percentile(
            values,
            percentile,
        )
    )

    near_fraction = float(
        np.mean(
            values
            <= max_distance_m
        )
    )

    detected = (
        valid_fraction
        >= min_valid_fraction
        and robust_distance
        <= max_distance_m
        and near_fraction
        >= min_near_fraction
    )

    # --------------------------------------------------------------
    # Conservative confidence
    # --------------------------------------------------------------

    distance_score = float(
        np.clip(
            (
                max_distance_m
                - robust_distance
            )
            / max_distance_m,
            0.0,
            1.0,
        )
    )

    coverage_score = float(
        np.clip(
            (
                valid_fraction
                - min_valid_fraction
            )
            / 0.50,
            0.0,
            1.0,
        )
    )

    concentration_score = float(
        np.clip(
            near_fraction
            / 0.25,
            0.0,
            1.0,
        )
    )

    confidence = (
        0.50 * distance_score
        + 0.25 * coverage_score
        + 0.25 * concentration_score
    )

    return {
        "detected": bool(
            detected
        ),
        "distance_m": (
            robust_distance
            if detected
            else None
        ),
        "confidence": (
            float(confidence)
            if detected
            else 0.0
        ),
        "valid_fraction": (
            valid_fraction
        ),
        "near_fraction": (
            near_fraction
        ),
        "roi": {
            "x0": x0,
            "x1": x1,
            "y0": 0,
            "y1": roi_h,
        },
    }


# ============================================================================
# Drop-off detection helpers
# ============================================================================

def _row_depth_profile(
    roi,
    min_valid_fraction=DROPOFF_MIN_VALID_FRACTION,
):
    """
    Calculate a robust depth value for each image row.

    Median depth is used because the objective is to estimate the dominant
    ground/surface depth, rather than the nearest object pixel.
    """
    rows, cols = roi.shape

    result = np.full(
        rows,
        np.nan,
        dtype=np.float32,
    )

    minimum_valid = max(
        3,
        int(
            round(
                cols
                * min_valid_fraction
            )
        ),
    )

    for y in range(rows):
        row = roi[y]

        valid = (
            np.isfinite(row)
            & (row > 0.02)
        )

        if int(
            valid.sum()
        ) < minimum_valid:
            continue

        result[y] = float(
            np.median(
                row[valid]
            )
        )

    return result


def _fill_nan_profile(
    values,
):
    """
    Linearly fill internal gaps in a 1-D depth profile.
    """
    values = np.asarray(
        values,
        dtype=np.float32,
    )

    valid = np.isfinite(
        values
    )

    if int(valid.sum()) < 4:
        return None

    x = np.arange(
        len(values)
    )

    return np.interp(
        x,
        x[valid],
        values[valid],
    ).astype(
        np.float32
    )


def _smooth_profile(
    values,
    window=DROPOFF_SMOOTH_WINDOW,
):
    """
    Moving-average smoothing of a 1-D depth profile.
    """
    if (
        window <= 1
        or len(values) < 3
    ):
        return values

    window = min(
        int(window),
        len(values),
    )

    kernel = (
        np.ones(
            window,
            dtype=np.float32,
        )
        / window
    )

    # Replicate the edges before convolving so the first/last rows are not
    # dragged toward zero (a boundary artifact of zero-padded convolution
    # that can fabricate or hide a discontinuity at the ROI border).
    pad = window // 2

    padded = np.pad(
        values,
        pad,
        mode="edge",
    )

    return np.convolve(
        padded,
        kernel,
        mode="valid",
    )[:len(values)]


# ============================================================================
# Drop-off detector
# ============================================================================

def detect_dropoff(
    depth_map,
    *,
    start_fraction=DROPOFF_START_FRAC,
    end_fraction=DROPOFF_END_FRAC,
    corridor_fraction=DROPOFF_CORRIDOR_FRAC,
    jump_threshold_m=DROPOFF_JUMP_M,
    ratio_threshold=DROPOFF_RATIO,
):
    """
    Detect a likely descending step, curb or drop-off.

    Geometric assumption:

        normal ground:
            depth changes relatively smoothly down the image.

        drop-off:
            the ground observed after an image-row boundary becomes
            substantially farther away.

    Candidate requirements:

        absolute depth jump >= jump_threshold_m

        AND

        after_depth / before_depth >= ratio_threshold

    This is deliberately conservative. It does not attempt to classify
    the exact type of terrain hazard.
    """

    global _dropoff_streak

    depth_map = np.asarray(
        depth_map,
        dtype=np.float32,
    )

    if depth_map.ndim != 2:
        raise ValueError(
            "depth_map must be 2-D"
        )

    h, w = depth_map.shape

    y0 = max(
        0,
        int(
            round(
                h * start_fraction
            )
        ),
    )

    y1 = min(
        h,
        int(
            round(
                h * end_fraction
            )
        ),
    )

    corridor_w = max(
        1,
        int(
            round(
                w * corridor_fraction
            )
        ),
    )

    x0 = (
        w - corridor_w
    ) // 2

    x1 = x0 + corridor_w

    roi = depth_map[
        y0:y1,
        x0:x1
    ]

    row_depth = _row_depth_profile(
        roi
    )

    profile = _fill_nan_profile(
        row_depth
    )

    if profile is None:
        _dropoff_streak = 0

        return {
            "detected": False,
            "candidate": False,
            "confirmed": False,
            "distance_m": None,
            "confidence": 0.0,
            "reason": (
                "insufficient_valid_depth"
            ),
        }

    smooth = _smooth_profile(
        profile
    )

    n = len(smooth)

    comparison = (
        DROPOFF_COMPARISON_WINDOW
    )

    if n < (
        2 * comparison + 1
    ):
        _dropoff_streak = 0

        return {
            "detected": False,
            "candidate": False,
            "confirmed": False,
            "distance_m": None,
            "confidence": 0.0,
            "reason": (
                "insufficient_profile_length"
            ),
        }

    # ------------------------------------------------------------------
    # Geometry note (why the comparison is oriented this way):
    #
    #   Rows are ordered top -> bottom. On a normal forward-facing view the
    #   floor is FARTHER at the top of the ROI and NEARER at the bottom, so
    #   depth DECREASES as the row index increases.
    #
    #       far  = upper band  (smaller row index)  -> farther on flat floor
    #       near = lower band  (larger row index)   -> nearer  on flat floor
    #
    #   A descending drop-off opens an OCCLUSION GAP: just beyond the edge the
    #   visible ground drops away, so the upper (far) band reads much FARTHER
    #   than the lower (near) band predicts.  The signature is therefore a
    #   large POSITIVE (far - near), well beyond ordinary floor perspective.
    #
    #   (The previous version tested (after - before) >= +threshold, i.e. it
    #   required the LOWER band to be farther than the UPPER band. On a real
    #   forward-facing camera that never happens, so it could not fire.)
    # ------------------------------------------------------------------

    # Typical row-to-row change of the smooth floor profile. Used to tell a
    # genuine discontinuity apart from ordinary perspective foreshortening.
    local_gradient = float(
        np.median(
            np.abs(
                np.diff(smooth)
            )
        )
    ) + 1e-6

    best = None

    for i in range(
        comparison,
        n - comparison,
    ):
        far = float(
            np.median(
                smooth[
                    i - comparison:i
                ]
            )
        )

        near = float(
            np.median(
                smooth[
                    i:i + comparison
                ]
            )
        )

        # Anchor on the NEAR (edge) side: this is the last solid ground
        # before the drop, and the distance we will announce.
        if (
            near
            < DROPOFF_MIN_SURFACE_M
        ):
            continue

        if (
            near
            > DROPOFF_MAX_SURFACE_M
        ):
            continue

        # Positive occlusion gap: how much farther the upper band sits.
        jump = (
            far - near
        )

        ratio = (
            far
            / max(
                near,
                1e-6,
            )
        )

        # What a smooth (continuous) floor would produce over this window.
        expected_gap = (
            local_gradient
            * comparison
        )

        if jump < jump_threshold_m:
            continue

        if ratio < ratio_threshold:
            continue

        # Must clearly exceed ordinary perspective, not just be a big number
        # because we happen to be looking far down the corridor.
        if jump < (
            DROPOFF_GRAD_MULT
            * expected_gap
        ):
            continue

        # Larger, sharper discontinuities are preferred.
        normalized_jump = np.clip(
            (
                jump - expected_gap
            ) / 1.0,
            0.0,
            1.0,
        )

        normalized_ratio = np.clip(
            (
                ratio - 1.0
            ) / 0.75,
            0.0,
            1.0,
        )

        score = (
            0.60 * normalized_jump
            + 0.40 * normalized_ratio
        )

        if (
            best is None
            or score > best["score"]
        ):
            best = {
                "index": i,
                "near_m": near,
                "far_m": far,
                "delta_m": jump,
                "ratio": ratio,
                "score": float(
                    score
                ),
            }

    # ------------------------------------------------------------------------
    # No candidate
    # ------------------------------------------------------------------------

    if best is None:
        _dropoff_streak = 0

        return {
            "detected": False,
            "candidate": False,
            "confirmed": False,
            "distance_m": None,
            "confidence": 0.0,
        }

    # ------------------------------------------------------------------------
    # Candidate found.
    #
    # Require temporal confirmation. This protects against one-frame
    # depth-model discontinuities.
    # ------------------------------------------------------------------------

    _dropoff_streak += 1

    confirmed = (
        _dropoff_streak
        >= DROPOFF_CONFIRM_FRAMES
    )

    # Announce the distance to the EDGE (last solid ground), i.e. the near
    # side of the discontinuity -- that is where the user must stop.
    distance_m = (
        best["near_m"]
    )

    return {
        "detected": bool(
            confirmed
        ),
        "candidate": True,
        "confirmed": bool(
            confirmed
        ),
        "distance_m": float(
            distance_m
        ),
        "jump_m": float(
            best["delta_m"]
        ),
        "depth_ratio": float(
            best["ratio"]
        ),
        "confidence": float(
            np.clip(
                best["score"],
                0.0,
                1.0,
            )
        ),
        "row_index": int(
            best["index"]
            + y0
        ),
        "roi": {
            "x0": x0,
            "x1": x1,
            "y0": y0,
            "y1": y1,
        },
    }


# ============================================================================
# Reset
# ============================================================================

def reset_path_state():
    """
    Reset all path/depth temporal state.

    Call on camera restart.
    """
    global _last
    global _dropoff_streak
    global _staircase_streak

    _last = None
    _dropoff_streak = 0
    _staircase_streak = 0
"""
Attribute-rich natural-language narration builder.

Turns structured detection dicts into short, actionable spoken phrases in the style:
    "Person approaching, 2 metres to your center."
    "Two people ahead, one in pink, one in black."
    "Red chair, 1 metre to your right."

This replaces raw VLM captions for the periodic narration loop, giving full control
over what is said and keeping latency near-zero (no model call).
"""

from collections import defaultdict

# Numbers as words for small counts
_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _count_word(n):
    return _NUM_WORDS.get(n, str(n))


# Spoken escalation for TTC urgency bands (feature 3.3).
# A critical/high closing threat must SOUND different from a calm mention.
_BAND_PREFIX = {"critical": "Stop.", "high": "Warning."}


def _apply_urgency(core, band):
    """Capitalize the clause and prepend an urgency word for high/critical bands."""
    if not core:
        return ""
    core = core[0].upper() + core[1:]
    prefix = _BAND_PREFIX.get(band)
    return f"{prefix} {core}." if prefix else f"{core}."


def _single_phrase(det):
    """Build a phrase for one detection: 'red car approaching, 3 metres to your center'."""
    cls = det.get("class", "object")

    # Prepend color if available
    color = det.get("color")
    noun = f"{color} {cls}" if color else cls

    # Motion
    motion_word = {
        "approaching": "approaching",
        "crossing": "crossing",
        "moving away": "moving away",
    }.get(det.get("motion", "still"))
    head = f"{noun} {motion_word}" if motion_word else noun

    # Distance + side (mirror the hazard narrators' <1 m wording)
    dist = det.get("distance")
    side = det.get("side", "front")
    side_word = "center" if side == "center" else side
    if dist is not None:
        try:
            dist = float(dist)
            if dist < 1.0:
                tail = f"less than one metre to your {side_word}"
            else:
                unit = "metre" if dist < 1.5 else "metres"
                tail = f"{dist:.0f} {unit} to your {side_word}"
        except (TypeError, ValueError):
            tail = f"to your {side_word}"
    else:
        tail = f"to your {side_word}"

    return f"{head}, {tail}"


def _group_phrase(dets):
    """Group same-class objects: 'two people ahead, one in pink, one in black'."""
    cls = dets[0].get("class", "object")
    n = len(dets)

    # Plural handling for people
    plural = "people" if cls == "person" else f"{cls}s"
    head = f"{_count_word(n)} {plural}"

    # Common side if they share it
    sides = {d.get("side", "front") for d in dets}
    if len(sides) == 1:
        side = sides.pop()
        head += f" {'ahead' if side == 'center' else 'to your ' + side}"

    # Add colors if distinct and available
    colors = [d.get("color") for d in dets if d.get("color")]
    if len(colors) == n:
        color_str = ", ".join(f"one in {c}" for c in colors)
        return f"{head}, {color_str}"

    return head


def narrate(priority_dets):
    """
    Build the final spoken sentence from prioritized detections.

    High/critical TTC bands (feature 3.3) are escalated with "Warning."/"Stop.".
    Same-class objects are grouped ONLY when all are still — grouping a moving
    threat would drop its motion and distance, which the user needs.

    Args:
        priority_dets: list of top-priority detection dicts

    Returns:
        spoken string. "Path clear." if nothing to announce.
    """
    if not priority_dets:
        return "Path clear."

    # Group by class to enable counting
    by_class = defaultdict(list)
    for d in priority_dets:
        by_class[d.get("class", "object")].append(d)

    sentences = []
    for cls, dets in by_class.items():
        moving = [d for d in dets
                  if d.get("motion", "still") in ("approaching", "crossing")]
        if len(dets) >= 2 and not moving:
            # calm, same-class cluster -> compact group phrase, no urgency word
            sentences.append(_apply_urgency(_group_phrase(dets), "none"))
        else:
            for d in dets:
                sentences.append(
                    _apply_urgency(_single_phrase(d),
                                   d.get("urgency_band", "none"))
                )

    return " ".join(s for s in sentences if s)


def narrate_find(target, bbox, side, dist):
    """
    Build a guiding sentence for the 'find my X' feature.

    Args:
        target: object name the user asked for
        bbox: [x1,y1,x2,y2] or None if not found
        side: 'left'/'center'/'right'
        dist: distance in metres or None

    Returns:
        spoken guidance string
    """
    if bbox is None:
        return f"I cannot find a {target} right now. Try moving your camera slowly."

    side_word = "straight ahead" if side == "center" else f"to your {side}"
    if dist is not None:
        if dist < 0.6:
            reach = "within arm's reach"
            return f"{target} found, {reach}, {side_word}."
        return f"{target} found, {dist:.0f} metres {side_word}."
    return f"{target} found, {side_word}."


def narrate_path(verdict):
    """
    Build a spoken phrase from a clear-path verdict (see engine/path.py).

    Args:
        verdict: dict with 'clear', 'obstacle_m', 'advice', 'advice_str'

    Returns:
        spoken string, or "" if there is nothing to say.
    """
    if verdict is None:
        return ""
    if verdict["clear"]:
        return "Path clear."
    obstacle_m = verdict.get("obstacle_m")
    dist_str = f"{obstacle_m:.0f} metres" if obstacle_m else "just ahead"
    advice = verdict.get("advice_str", "")
    if verdict["advice"] == "stop":
        return f"Stop. Obstacle {dist_str} ahead, {advice}."
    return f"Obstacle {dist_str} ahead, {advice}."


def narrate_overhead(result):
    """
    Build spoken warning for a detected head-height / upper-region obstacle.

    Args:
        result: dict returned by engine.path.analyze_overhead()

    Returns:
        Spoken warning string, or "" if no confirmed hazard exists.
    """
    if not result or not result.get("detected", False):
        return ""

    distance = result.get("distance_m")

    if distance is None:
        return "Head height obstacle ahead. Stop."

    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return "Head height obstacle ahead. Stop."

    if distance < 1.0:
        return (
            "Head height obstacle ahead, "
            "less than one metre. Stop."
        )

    unit = "metre" if distance < 1.5 else "metres"

    return (
        f"Head height obstacle ahead, "
        f"{distance:.0f} {unit}. Stop."
    )


def narrate_dropoff(result):
    """
    Build spoken warning for a confirmed descending step / curb / drop-off.

    Args:
        result: dict returned by engine.path.detect_dropoff()

    Returns:
        Spoken warning string, or "" if no confirmed hazard exists.
    """
    if not result or not result.get("detected", False):
        return ""

    distance = result.get("distance_m")

    if distance is None:
        return "Caution, step down ahead. Stop."

    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return "Caution, step down ahead. Stop."

    if distance < 1.0:
        return (
            "Caution, step down ahead, "
            "less than one metre. Stop."
        )

    unit = "metre" if distance < 1.5 else "metres"

    return (
        f"Caution, step down ahead, "
        f"{distance:.0f} {unit}. Stop."
    )


def narrate_staircase(result):
    """
    Build spoken warning for a confirmed staircase (ascending or descending).

    Args:
        result: dict returned by engine.path.detect_staircase(), optionally
                with a "color" key set by the caller.

    Returns:
        Spoken warning string, or "" if no confirmed hazard exists.
    """
    if not result or not result.get("detected", False):
        return ""

    color = result.get("color")
    noun = f"{color} staircase" if color else "staircase"

    distance = result.get("distance_m")

    if distance is None:
        return f"Caution, {noun} ahead. Stop."

    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return f"Caution, {noun} ahead. Stop."

    if distance < 1.0:
        return (
            f"Caution, {noun} ahead, "
            "less than one metre. Stop."
        )

    unit = "metre" if distance < 1.5 else "metres"

    return (
        f"Caution, {noun} ahead, "
        f"{distance:.0f} {unit}. Stop."
    )


def narrate_read(text):

    """
    Build a spoken phrase for the 'read this' OCR intent.

    Args:
        text: recognized text string (may be empty)

    Returns:
        spoken string
    """
    text = (text or "").strip()
    if not text:
        return "I could not find any readable text. Try holding the camera steady and closer."
    return f"The text reads: {text}"
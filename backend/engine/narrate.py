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


# ----------------------------------------------------------------------------
# Orientation & mobility wording (priority mode only).
#
# O&M instructors give bearings on a clock face and distances in paces, because
# both are egocentric and need no external reference. "left/right + 2.3 metres"
# is a sighted description of a scene; "11 o'clock, about three steps" is an
# instruction the user can act on without translating anything.
#
# Only the forward arc is used: a walking user cannot act on 6 o'clock, and the
# camera cannot see it anyway.
# ----------------------------------------------------------------------------

# How far the frame edges bend away from 12 o'clock. Raising this widens the
# spread (frame edge reads as a sharper bearing); lowering it narrows it.
_CLOCK_SPREAD = 2

_CLOCK_HOURS = {-2: 10, -1: 11, 0: 12, 1: 1, 2: 2}

# Average pace length in metres, used to convert distance into step counts.
_STEP_LENGTH_M = 0.75


def _clock_direction(cx, frame_w):
    """
    Map a bounding-box centre-x to a clock-face bearing.

    Args:
        cx: horizontal centre of the detection, in pixels
        frame_w: frame width in pixels

    Returns:
        e.g. "11 o'clock", or None when cx/frame_w are unusable (the caller then
        falls back to left/right wording rather than saying nothing).
    """
    try:
        cx = float(cx)
        frame_w = float(frame_w)
    except (TypeError, ValueError):
        return None

    if frame_w <= 0:
        return None

    x = (cx / frame_w) * 2 - 1                      # normalise to [-1, 1]
    offset = int(round(x * _CLOCK_SPREAD))
    offset = max(-_CLOCK_SPREAD, min(_CLOCK_SPREAD, offset))

    hour = _CLOCK_HOURS.get(offset)
    if hour is None:
        return None
    return f"{hour} o'clock"


def _steps_from_metres(m, step_len=_STEP_LENGTH_M):
    """
    Convert a distance in metres into a spoken step count.

    Returns:
        "right in front of you" / "one step" / "about three steps", or None when
        the distance is missing or unparseable.
    """
    if m is None:
        return None
    try:
        m = float(m)
    except (TypeError, ValueError):
        return None

    if m < step_len:
        return "right in front of you"

    n = max(1, int(round(m / step_len)))
    if n == 1:
        return "one step"
    return f"about {_count_word(n)} steps"


def _om_location(det, frame_w):
    """
    Build the clock-face + step-count location clause for one detection.

    Returns:
        e.g. "at 11 o'clock, about three steps", or None if no bearing can be
        derived (caller falls back to the metre/side wording).
    """
    clock = _clock_direction(det.get("cx"), frame_w)
    if not clock:
        return None
    steps = _steps_from_metres(det.get("distance"))
    return f"at {clock}, {steps}" if steps else f"at {clock}"


def _nearest(dets):
    """Closest detection; missing/unparseable distances sort last."""
    def sort_key(d):
        try:
            return float(d.get("distance"))
        except (TypeError, ValueError):
            return float("inf")
    return min(dets, key=sort_key)


def _single_phrase(det, frame_w=None, use_clockface=False):
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

    # O&M wording: 'chair at 11 o'clock, about three steps'.
    if use_clockface and frame_w:
        location = _om_location(det, frame_w)
        if location:
            return f"{head} {location}"
        # No usable cx — fall through to the metre/side wording below.

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


def _group_phrase(dets, frame_w=None, use_clockface=False):
    """Group same-class objects: 'two people ahead, one in pink, one in black'."""
    cls = dets[0].get("class", "object")
    n = len(dets)

    # Plural handling for people
    plural = "people" if cls == "person" else f"{cls}s"
    head = f"{_count_word(n)} {plural}"

    # O&M wording uses the nearest member's bearing — that is the one the user
    # will reach first, so it is the one worth steering by.
    located = False
    if use_clockface and frame_w:
        location = _om_location(_nearest(dets), frame_w)
        if location:
            head += f" {location}"
            located = True

    # Common side if they share it
    if not located:
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


def narrate(priority_dets, frame_w=None, use_clockface=False):
    """
    Build the final spoken sentence from prioritized detections.

    High/critical TTC bands (feature 3.3) are escalated with "Warning."/"Stop.".
    Same-class objects are grouped ONLY when all are still — grouping a moving
    threat would drop its motion and distance, which the user needs.

    Args:
        priority_dets: list of top-priority detection dicts
        frame_w: frame width in pixels; required for clock-face bearings
        use_clockface: speak O&M wording (clock-face bearing + step count)
            instead of side + metres. Requires frame_w. Left False for the
            naive baseline so its wording stays fixed.

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
            sentences.append(
                _apply_urgency(
                    _group_phrase(dets, frame_w=frame_w, use_clockface=use_clockface),
                    "none",
                )
            )
        else:
            for d in dets:
                sentences.append(
                    _apply_urgency(_single_phrase(d,
                                                  frame_w=frame_w,
                                                  use_clockface=use_clockface),
                                   d.get("urgency_band", "none"))
                )

    return " ".join(s for s in sentences if s)


def _spoken_target(target, possessive=False):
    target = str(target or "object").strip().lower()
    for article in ("your ", "the ", "a ", "an "):
        if target.startswith(article):
            target = target[len(article):]
            break
    return f"your {target}" if possessive else f"the {target}"


def _vertical_position(bbox, frame_shape=None):
    if not bbox or not frame_shape:
        return "hand level"
    height = float(frame_shape[0])
    center_y = (float(bbox[1]) + float(bbox[3])) / 2.0
    if center_y < 0.36 * height:
        return "above hand level"
    if center_y > 0.70 * height:
        return "below hand level"
    return "hand level"


def _position_phrase(side, vertical):
    if side == "left":
        direction = "slightly to your left"
    elif side == "right":
        direction = "slightly to your right"
    else:
        direction = "straight ahead"
    return f"{direction}, at about {vertical}"


def _reach_instruction(side, vertical, dist):
    if dist is None:
        return "Keep the camera pointed at it and move closer slowly before reaching."
    try:
        dist = float(dist)
    except (TypeError, ValueError):
        return "Keep the camera pointed at it and move closer slowly before reaching."
    if dist > 0.9:
        return "It is beyond comfortable reach. Move closer slowly, then ask me again before reaching."

    if side == "right":
        action = "Extend your right hand slightly forward"
    elif side == "left":
        action = "Extend your left hand slightly forward"
    else:
        action = "Reach straight ahead slowly"

    if vertical == "above hand level":
        action += " and raise it a little"
    elif vertical == "below hand level":
        action += " and lower it a little"
    return f"{action}."


def _distance_phrase(dist):
    if dist is None:
        return None
    try:
        dist = float(dist)
    except (TypeError, ValueError):
        return None
    if dist < 0.9:
        return "within arm's reach"
    if dist < 1.0:
        return "less than one metre away"
    unit = "metre" if dist < 1.5 else "metres"
    return f"about {dist:.1f} {unit} away"


def narrate_find(
    target,
    bbox,
    side,
    dist,
    relation=None,
    frame_shape=None,
    possessive=False,
    tentative=False,
    include_action=True,
):
    """
    Build a guiding sentence for the 'find my X' feature.

    Args:
        target: object name the user asked for
        bbox: [x1,y1,x2,y2] or None if not found
        side: 'left'/'center'/'right'
        dist: distance in metres or None
        relation: optional support relation such as 'on the table'
        frame_shape: image shape used for above/below hand-level guidance
        possessive: say 'your bottle' instead of 'the bottle'
        tentative: use cautious wording for open-vocabulary model matches
        include_action: append a conservative reach/move instruction

    Returns:
        spoken guidance string
    """
    spoken_target = _spoken_target(target, possessive=possessive)
    if bbox is None:
        return (
            f"I cannot see {spoken_target} in the current view. "
            "Slowly pan the camera from left to right, keeping it level, then ask me again."
        )

    lead = (
        f"I can see what appears to be {spoken_target}."
        if tentative else f"I found {spoken_target}."
    )
    vertical = _vertical_position(bbox, frame_shape)
    details = []
    if relation:
        details.append(f"It appears to be {relation}")
    else:
        details.append("It is")
    details.append(_position_phrase(side, vertical))
    distance = _distance_phrase(dist)
    if distance:
        details.append(distance)
    location = ", ".join(details) + "."

    if not include_action:
        return f"{lead} {location}"
    return f"{lead} {location} {_reach_instruction(side, vertical, dist)}"


def narrate_surface_contents(surface, items, exclude_target=None):
    """Speak a compact, cautious list of items associated with a surface."""
    labels = [str(item.get("label", "")).strip() for item in items if item.get("label")]
    if not labels:
        if exclude_target:
            return f"I do not see another clear item on the {surface} right now."
        return f"I cannot confirm any clear items on the {surface} in this view."
    if len(labels) == 1:
        listing = labels[0]
    else:
        listing = ", ".join(labels[:-1]) + f", and {labels[-1]}"
    return f"On the {surface}, I can see what appears to be {listing}."


def narrate_nearby(target, nearby_item):
    if not nearby_item:
        return f"I cannot identify another clear item next to {_spoken_target(target, True)}."
    relation = nearby_item.get("relation")
    label = nearby_item.get("label", "another object")
    target_name = _spoken_target(target, True)
    if relation in {"left", "right"}:
        relation_text = f"to the {relation} of {target_name}"
    elif relation in {"above", "below"}:
        relation_text = f"{relation} {target_name}"
    else:
        relation_text = f"near {target_name}"
    return f"The closest clear item is the {label}, {relation_text}."


def narrate_scene_description(caption, max_words=48):
    """Turn Florence's image-caption style into a short first-person response."""
    text = " ".join(str(caption or "").strip().split())
    if not text:
        return "I cannot describe the current view clearly."
    lowered = text.lower()
    for prefix in ("the image shows ", "the image depicts ", "in the image, ", "in this image, "):
        if lowered.startswith(prefix):
            text = text[len(prefix):]
            break
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" ,;:") + "."
    if text:
        text = text[0].lower() + text[1:]
    return f"I can see {text}".rstrip()


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
        return ""
    obstacle_m = verdict.get("obstacle_m")
    if obstacle_m is None:
        return ""

    try:
        obstacle_m = float(obstacle_m)
    except (TypeError, ValueError):
        return ""

    if obstacle_m < 1.0:
        dist_str = "less than one metre"
    else:
        unit = "metre" if obstacle_m < 1.5 else "metres"
        dist_str = f"{obstacle_m:.0f} {unit}"

    advice = verdict.get("advice_str", "")
    if verdict["advice"] == "stop":
        return f"Stop. Obstacle {dist_str} ahead."
    return f"Obstacle {dist_str} ahead. {advice.capitalize()}."


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

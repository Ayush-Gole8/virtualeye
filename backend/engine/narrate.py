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


def _single_phrase(det):
    """Build a phrase for one detection."""
    parts = []
    cls = det.get("class", "object")

    # Prepend color if available
    color = det.get("color")
    noun = f"{color} {cls}" if color else cls
    parts.append(noun)

    # Motion
    motion = det.get("motion", "still")
    if motion == "approaching":
        parts.append("approaching")
    elif motion == "crossing":
        parts.append("crossing")
    elif motion == "moving away":
        parts.append("moving away")

    # Distance + side
    dist = det.get("distance")
    side = det.get("side", "front")
    side_word = "center" if side == "center" else side
    if dist is not None:
        unit = "metre" if dist < 1.5 else "metres"
        parts.append(f"{dist:.0f} {unit} to your {side_word}")
    else:
        parts.append(f"to your {side_word}")

    return " ".join(parts)


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

    phrases = []
    for cls, dets in by_class.items():
        if len(dets) >= 2:
            phrases.append(_group_phrase(dets))
        else:
            phrases.append(_single_phrase(dets[0]))

    return ". ".join(p.capitalize() for p in phrases) + "."


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

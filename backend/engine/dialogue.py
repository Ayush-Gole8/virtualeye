"""Pure conversation and spatial helpers for voice-first scene questions."""

import re
import threading
import time


SESSION_TTL_SECONDS = 15 * 60
_TARGET_PRONOUNS = {"it", "that", "that one", "the object", "the item"}
_SURFACE_ALIASES = {
    "dining table": "table", "coffee table": "table", "side table": "table",
    "table": "table", "desk": "desk", "countertop": "counter",
    "counter": "counter", "shelf": "shelf", "bed": "bed", "chair": "chair",
    "couch": "couch", "sofa": "couch", "bench": "bench",
}
_FIND_PATTERNS = (
    r"\bwhere\s+(?:can|could|would)\s+i\s+(?:please\s+)?find\s+(.+)$",
    r"\bwhere\s+(?:is|are)\s+(.+)$",
    r"\bwhere's\s+(.+)$",
    r"\b(?:can|could|would)\s+you\s+(?:please\s+)?(?:find|locate|look\s+for|see)\s+(.+)$",
    r"\b(?:please\s+)?find\s+me\s+(.+)$",
    r"\b(?:please\s+)?(?:help\s+me\s+)?(?:find|locate|look\s+for)\s+(.+)$",
    r"\b(?:do|can)\s+you\s+see\s+(.+)$",
    r"\bis\s+there\s+(.+)$",
    r"\bis\s+(?:my|the|a|an)\s+(.+?)\s+(?:here|visible|in view)$",
)
_SCENE_QUESTION_MARKERS = (
    "find ", "locate ", "look for", "where is", "where are", "where can i find",
    "can you see", "do you see", "is there",
    "what do you see", "what can you see",
    "describe", "what is around", "what's around", "what is here", "what's here",
    "what is on", "what's on", "anything on", "anything else", "what else",
    "next to", "beside", "near it", "how far", "what distance", "which side",
    "what side", "left or right", "within reach", "can i reach", "how do i reach",
    "how should i reach", "check again", "try again", "look again", "see it now",
    "where is it now", "how many", "count ", "what is to my", "what's to my",
    "what is in front", "what's in front",
)


def normalize_question(question):
    text = str(question or "").lower().replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sanitize_session_id(session_id):
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "", str(session_id or ""))[:80]
    return cleaned or "default"


def is_scene_question(question):
    text = normalize_question(question)
    presence_question = re.match(
        r"^is\s+(?:my|the|a|an)\s+.+\s+(?:here|visible|in view)$",
        text,
    )
    return bool(presence_question) or any(marker in text for marker in _SCENE_QUESTION_MARKERS)


def _clean_target(target):
    target = normalize_question(target)
    target = re.sub(r"^(?:my|the|a|an|some)\s+", "", target)
    target = re.sub(r"\s+(?:please|for me|right now)$", "", target)
    target = re.sub(r"\s+in\s+the\s+(?:current\s+)?(?:view|frame|scene)$", "", target)
    target = re.sub(r"\s+around\s+me$", "", target)
    target = re.sub(r"\s+(?:is|are)$", "", target)
    return target.strip(" -")


def extract_find_target(question):
    text = normalize_question(question)
    for pattern in _FIND_PATTERNS:
        match = re.search(pattern, text)
        if match:
            target = _clean_target(match.group(1))
            return target or None
    return None


def extract_surface(question):
    text = normalize_question(question)
    for alias in sorted(_SURFACE_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return _SURFACE_ALIASES[alias]
    return None


def _followup_target(text, context):
    patterns = (
        r"\bhow\s+far(?:\s+away)?\s+(?:is|are)\s+(.+)$",
        r"\b(?:which|what)\s+side\s+(?:is|are)\s+(.+)$",
        r"\bcan\s+i\s+reach\s+(.+)$",
        r"\bhow\s+(?:do|should|can)\s+i\s+(?:reach|get)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        target = _clean_target(match.group(1))
        if target in _TARGET_PRONOUNS:
            return context.get("last_target")
        return target or context.get("last_target")
    return context.get("last_target")


def surface_aliases(surface):
    canonical = _SURFACE_ALIASES.get(str(surface or "").lower(), str(surface or "").lower())
    aliases = [name for name, value in _SURFACE_ALIASES.items() if value == canonical]
    return aliases or [canonical]


def classify_scene_question(question, context=None):
    """Classify a spoken scene question and resolve conversational references."""
    context = context or {}
    text = normalize_question(question)
    explicit_surface = extract_surface(text)
    last_target = context.get("last_target")
    last_surface = context.get("last_surface")

    asks_for_surface_contents = any(phrase in text for phrase in (
        "what is on", "what's on", "what are on", "anything on",
        "anything else", "what else is on", "what else on",
    ))
    if asks_for_surface_contents and (explicit_surface or last_surface or " on it" in text):
        return {
            "intent": "surface_contents",
            "surface": explicit_surface or last_surface,
            "exclude_target": last_target if "else" in text else None,
        }

    if any(phrase in text for phrase in ("next to", "beside", "near it", "near that")):
        return {"intent": "nearby", "target": extract_find_target(text) or last_target}

    if any(phrase in text for phrase in ("check again", "try again", "look again", "see it now", "where is it now")):
        return {"intent": "locate", "target": last_target, "possessive": True, "repeat": True}

    if any(phrase in text for phrase in ("how far", "what distance", "distance is")):
        return {"intent": "distance", "target": _followup_target(text, context)}

    if any(phrase in text for phrase in ("which side", "what side", "left or right")):
        return {"intent": "side", "target": _followup_target(text, context)}

    if any(phrase in text for phrase in ("within reach", "can i reach", "how do i reach", "how should i reach", "how can i get")):
        return {"intent": "reach", "target": _followup_target(text, context)}

    if any(phrase in text for phrase in (
        "what do you see", "what can you see", "describe", "what is around",
        "what's around", "what is here", "what's here",
    )):
        return {"intent": "describe"}

    target = extract_find_target(text)
    if target in _TARGET_PRONOUNS:
        target = last_target
    if target:
        return {
            "intent": "locate",
            "target": target,
            "possessive": bool(re.search(r"\bmy\b", text)),
        }

    if any(phrase in text for phrase in ("how many", "count ", "number of")):
        return {"intent": "count"}

    if any(phrase in text for phrase in ("to my left", "on my left", "to my right", "on my right", "in front")):
        return {"intent": "region"}

    return {"intent": "summary"}


def canonical_label(label):
    """Normalize model labels for matching and spoken deduplication."""
    text = normalize_question(label)
    text = re.sub(r"^(?:a|an|the|one|two|three|several)\s+", "", text)
    text = re.sub(r"\s+(?:in|on|at|with)\s+the\s+(?:image|scene|background).*$", "", text)
    return text.strip()


def labels_match(first, second):
    """Fuzzy-enough label match for YOLO names and spoken object phrases."""
    first = canonical_label(first)
    second = canonical_label(second)
    if not first or not second:
        return False
    if first == second or first in second or second in first:
        return True
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    return bool(
        first_tokens and second_tokens
        and (first_tokens <= second_tokens or second_tokens <= first_tokens)
    )


def bbox_center(bbox):
    x1, y1, x2, y2 = map(float, bbox)
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def bbox_area(bbox):
    x1, y1, x2, y2 = map(float, bbox)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def bbox_supported_by(item_bbox, surface_bbox):
    """Geometrically test whether an item plausibly rests on a surface."""
    try:
        ix1, iy1, ix2, iy2 = map(float, item_bbox)
        sx1, sy1, sx2, sy2 = map(float, surface_bbox)
    except (TypeError, ValueError):
        return False

    surface_width = max(1.0, sx2 - sx1)
    surface_height = max(1.0, sy2 - sy1)
    item_center_x = (ix1 + ix2) / 2.0
    item_center_y = (iy1 + iy2) / 2.0
    item_bottom = iy2

    horizontally_supported = sx1 - 0.05 * surface_width <= item_center_x <= sx2 + 0.05 * surface_width
    near_surface_top = sy1 - 0.30 * surface_height <= item_bottom <= sy1 + 0.50 * surface_height
    item_above_surface_center = item_center_y <= sy1 + 0.60 * surface_height
    item_is_smaller = bbox_area(item_bbox) <= 0.60 * bbox_area(surface_bbox)
    return horizontally_supported and near_surface_top and item_above_surface_center and item_is_smaller


def dedupe_scene_items(items):
    """Drop invalid and duplicate region/detection items while preserving order."""
    unique = []
    for item in items or []:
        label = canonical_label(item.get("label") or item.get("class"))
        bbox = item.get("bbox")
        if not label or not bbox or len(bbox) != 4:
            continue
        if any(labels_match(label, existing["label"]) for existing in unique):
            continue
        unique.append({**item, "label": label, "bbox": list(map(float, bbox))})
    return unique


def items_on_surface(surface_bbox, items, surface_label, exclude_labels=None, limit=5):
    """Return visible items whose boxes plausibly rest on the chosen surface."""
    excluded = [surface_label] + list(exclude_labels or [])
    blocked_terms = {"person", "wall", "floor", "ceiling", "room"}
    matches = []
    for item in dedupe_scene_items(items):
        label = item["label"]
        if any(labels_match(label, excluded_label) for excluded_label in excluded if excluded_label):
            continue
        if any(term in label.split() for term in blocked_terms):
            continue
        if bbox_supported_by(item["bbox"], surface_bbox):
            matches.append(item)
        if len(matches) >= limit:
            break
    return matches


def relative_bbox_direction(reference_bbox, other_bbox):
    """Describe one box relative to another using a concise direction."""
    ref_x, ref_y = bbox_center(reference_bbox)
    other_x, other_y = bbox_center(other_bbox)
    dx = other_x - ref_x
    dy = other_y - ref_y
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "below" if dy > 0 else "above"


def nearest_scene_item(target_bbox, items, target_label=None):
    """Return the closest non-target item by normalized image-plane distance."""
    target_x, target_y = bbox_center(target_bbox)
    target_scale = max(1.0, bbox_area(target_bbox) ** 0.5)
    candidates = []
    for item in dedupe_scene_items(items):
        if target_label and labels_match(item["label"], target_label):
            continue
        if any(term in item["label"].split() for term in ("person", "wall", "floor", "ceiling")):
            continue
        item_x, item_y = bbox_center(item["bbox"])
        distance = (((item_x - target_x) ** 2 + (item_y - target_y) ** 2) ** 0.5) / target_scale
        candidates.append((distance, item))
    if not candidates:
        return None
    _, closest = min(candidates, key=lambda pair: pair[0])
    return {**closest, "relation": relative_bbox_direction(target_bbox, closest["bbox"])}


class DialogueMemoryStore:
    """Thread-safe, short-lived conversation context keyed by browser session."""

    def __init__(self, ttl_seconds=SESSION_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._sessions = {}
        self._lock = threading.Lock()

    def _purge_locked(self, now):
        expired = [
            session_id for session_id, value in self._sessions.items()
            if now - value.get("updated_at", now) > self.ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def get(self, session_id):
        session_id = sanitize_session_id(session_id)
        now = time.monotonic()
        with self._lock:
            self._purge_locked(now)
            value = self._sessions.get(session_id, {})
            return {key: item for key, item in value.items() if key != "updated_at"}

    def update(self, session_id, **values):
        session_id = sanitize_session_id(session_id)
        now = time.monotonic()
        with self._lock:
            self._purge_locked(now)
            current = self._sessions.setdefault(session_id, {})
            current.update(values)
            current["updated_at"] = now
            return {key: item for key, item in current.items() if key != "updated_at"}

    def reset(self, session_id=None):
        with self._lock:
            if session_id is None:
                self._sessions.clear()
            else:
                self._sessions.pop(sanitize_session_id(session_id), None)

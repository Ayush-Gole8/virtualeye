"""
Session telemetry for Virtual Eye user studies and safety evaluation.

Each analysed frame is appended as one JSON line:

{
    "ts": 1723...,
    "session": "s1",
    "mode": "priority",
    "latency_ms": 87.4,

    "n_dets": 3,
    "dets": [
        {
            "class": "person",
            "track_id": 4,
            "dist_m": 2.1,
            "motion": "approaching",
            "velocity_mps": -0.72,
            "closing_speed_mps": 0.72,
            "ttc_s": 2.9,
            "urgency_band": "high",
            "ttc_decreasing": true,
            "ttc_high_confirmed": true,
            "priority": 31.0
        }
    ],

    "safety": {
        "overhead": {
            "detected": true,
            "distance_m": 1.2,
            "confidence": 0.81
        },
        "dropoff": {
            "detected": false,
            "distance_m": null,
            "confidence": 0.0
        }
    },

    "path": {
        "clear": false,
        "obstacle_m": 1.4,
        "advice": "left"
    },

    "speech": "...",
    "speech_events": [
        "overhead"
    ],
    "words": 7
}

The log is intentionally frame-oriented so the resulting JSONL can be
analysed offline for latency, false alerts, TTC transitions, debounce
behavior, and naive-vs-priority comparisons.

Stdlib only.
Thread-safe writes.
"""

from __future__ import annotations

import json
import os
import threading
import time


DEFAULT_LOG_DIR = "study_logs"


_lock = threading.Lock()

_session = None
_fh = None
_log_path = None


def start_session(
    session_id=None,
    log_dir=DEFAULT_LOG_DIR,
):
    """
    Open or retain the JSONL file for the given session.

    Repeated calls with the same session ID are no-ops.

    Passing a different session ID closes the previous session and
    opens a new file.
    """
    global _session
    global _fh
    global _log_path

    if (
        _session == session_id
        and _fh is not None
    ):
        return _fh

    stop_session()

    os.makedirs(
        log_dir,
        exist_ok=True,
    )

    session_id = (
        session_id
        or time.strftime(
            "session_%Y%m%d_%H%M%S"
        )
    )

    path = os.path.join(
        log_dir,
        f"{session_id}.jsonl",
    )

    _fh = open(
        path,
        "a",
        encoding="utf-8",
    )

    _session = session_id
    _log_path = path

    print(
        f"[TELEMETRY] logging to {path}"
    )

    return _fh


def log_frame(payload):
    """
    Append one JSON object as one JSONL record.

    Payload must be JSON-serializable.

    Silently skips when no session is active.
    """
    if payload is None:
        return

    with _lock:
        if _fh is None:
            return

        _fh.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

        _fh.flush()


def current_session():
    """
    Return active session ID or empty string.
    """
    return _session or ""


def current_log_path():
    """
    Return active log path or empty string.
    """
    return _log_path or ""


def stop_session():
    """
    Flush and close current telemetry file.
    Safe to call when no session exists.
    """
    global _fh
    global _session
    global _log_path

    with _lock:
        if _fh is not None:
            try:
                _fh.flush()
            finally:
                _fh.close()

        _fh = None
        _session = None
        _log_path = None
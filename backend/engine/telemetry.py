"""
Session telemetry for the naive-vs-priority user study.

Appends one JSON line per analysed frame to study_logs/<session>.jsonl:

    {"ts": 1723..., "session": "s1", "mode": "priority", "latency_ms": 87,
     "n_dets": 3, "dets": [{"class": "person", "dist": 1.2, "motion": "still"}],
     "speech": "Red chair, 1 metre to your right.", "words": 7,
     "path": {"clear": false, "obstacle_m": 1.4, "advice": "left"}}

Analysis happens offline with analyze_study.py — no live dashboard needed.
The study log itself becomes an appendix artifact for the 40-day report.

Stdlib only, so it never disturbs the model stack. Thread-safe writes.
"""

import json
import os
import threading
import time

DEFAULT_LOG_DIR = "study_logs"

_lock = threading.Lock()
_session = None
_fh = None


def start_session(session_id=None, log_dir=DEFAULT_LOG_DIR):
    """
    Open (or keep) a JSONL file for the given session id. Call once per
    /analyze_frame with the session name; repeated calls with the same id are
    no-ops. Pass a fresh id to rotate to a new file.
    """
    global _session, _fh
    if _session == session_id and _fh is not None:
        return _fh
    stop_session()
    os.makedirs(log_dir, exist_ok=True)
    session_id = session_id or time.strftime("session_%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"{session_id}.jsonl")
    _fh = open(path, "a", encoding="utf-8")
    _session = session_id
    print(f"[TELEMETRY] logging to {path}")
    return _fh


def log_frame(payload):
    """
    Append one frame record. Payload must be JSON-serializable (dict).
    Silently skips if no session has been started.
    """
    if _fh is None:
        return
    with _lock:
        _fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        _fh.flush()


def current_session():
    """Name of the active session file ('' if none)."""
    return _session or ""


def stop_session():
    """Flush + close the current log file. Safe to call anytime."""
    global _fh, _session
    if _fh is not None:
        with _lock:
            _fh.close()
        _fh = None
    _session = None

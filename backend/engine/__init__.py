"""
Virtual Eye 3.0 perception engine.

UI-free modules that turn a camera frame into prioritized, spatial, attribute-rich
guidance. Orchestrated by backend/server.py.

Modules:
    depth     - metric depth (Depth Anything V2)
    motion    - approaching/crossing/still + closing speed + TTC from ByteTrack
    color     - dominant color naming (HSV)
    priority  - cognitive-load-aware scoring + selection, TTC-ranked (core contribution)
    path      - clear-path / obstacle-in-corridor navigation from the depth map
    narrate   - attribute-rich sentence builder (objects, path, find, read)
    ocr       - on-demand EasyOCR 'read this' text recognition (en/hi/mr)
    telemetry - JSONL per-frame logging for the naive-vs-priority user study
    vlm       - Florence-2 for scene Q&A and open-vocabulary object finding
    dialogue  - conversational NLU + short-lived session memory for voice Q&A
"""

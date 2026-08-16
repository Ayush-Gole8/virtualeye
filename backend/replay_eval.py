"""
replay_eval.py — Offline evaluation harness for Virtual Eye 3.0.

Feeds a pre-recorded walking video into the running Flask server exactly the way
the live frontend does (one frame ~every second), so the perception engine's
motion/TTC/priority logic behaves the same as in a live demo. The server logs
telemetry automatically to backend/study_logs/<session_id>.jsonl; run
analyze_study.py afterwards to get the naive-vs-priority table.

WHY PACING MATTERS:
    Motion dt comes from the `frame_ts` we send (the frame's VIDEO time), so
    closing speed and TTC are reproducible: replaying the same clip at a
    different --interval pacing yields the same TTC columns.

    We still sample every `--interval` seconds of video AND sleep so each POST is
    ~`--interval` apart in REAL time, because the announcement cooldowns and
    hazard debounce on the server are still wall-clock based. Removing the sleep
    would collapse those and change which lines get spoken.

USAGE (run the server first: python server.py):
    # One clip in priority mode:
    python replay_eval.py eval_videos/hallway.mp4 --mode priority

    # Same clip in naive mode (for the A/B comparison):
    python replay_eval.py eval_videos/hallway.mp4 --mode naive

    # Custom server / cadence / session name:
    python replay_eval.py eval_videos/clip.mp4 --mode priority \
        --url http://localhost:5000 --interval 1.0 --session hallway_priority

Then:
    python analyze_study.py study_logs/*.jsonl

Requires: opencv-python, requests  (both already in the backend venv).
"""

import argparse
import os
import sys
import time

import cv2
import requests


def replay(video_path, url, mode, interval, session_id, lang):
    if not os.path.exists(video_path):
        sys.exit(f"[ERROR] video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"[ERROR] could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # How many source frames to skip so we sample every `interval` seconds of video.
    stride = max(1, int(round(fps * interval)))

    print(f"[INFO] {os.path.basename(video_path)}: {fps:.1f} fps, "
          f"{total} frames (~{total / fps:.1f}s)")
    print(f"[INFO] sampling 1 frame every {stride} ({interval:.2f}s of video)")
    print(f"[INFO] mode={mode}  session_id={session_id}")
    print(f"[INFO] POSTing to {url}/analyze_frame\n")

    analyze = f"{url.rstrip('/')}/analyze_frame"
    headers = {"ngrok-skip-browser-warning": "true"}  # harmless on localhost

    frame_idx = 0
    sent = 0
    t_wall_start = time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % stride == 0:
            loop_start = time.time()

            # Match the frontend: downscale a bit and JPEG-encode.
            frame_small = cv2.resize(frame, (480, 360))
            ok_enc, buf = cv2.imencode(".jpg", frame_small,
                                       [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok_enc:
                frame_idx += 1
                continue

            files = {"frame": ("frame.jpg", buf.tobytes(), "image/jpeg")}
            # frame_ts is this frame's position in VIDEO time. The server feeds it
            # to motion.update_motion as dt's clock, so velocity/TTC depend on the
            # recording, not on processing speed. Derived from frame_idx rather
            # than the sent counter so a failed POST cannot shift later timestamps.
            data = {
                "mode": mode,
                "session_id": session_id,
                "lang": lang,
                "frame_ts": f"{frame_idx / fps:.6f}",
            }

            try:
                r = requests.post(analyze, files=files, data=data,
                                  headers=headers, timeout=60)
                r.raise_for_status()
                out = r.json()
            except Exception as e:  # noqa: BLE001
                print(f"[t={sent:>3}s] REQUEST FAILED: {e}")
                frame_idx += 1
                continue

            sent += 1
            speech = (out.get("speech") or "").strip()
            path = out.get("path") or {}
            n = len(out.get("detections") or [])
            path_note = ""
            if path:
                path_note = "  path=CLEAR" if path.get("clear") else \
                            f"  path=BLOCKED@{path.get('obstacle_m')}m->{path.get('advice')}"
            print(f"[t={sent:>3}s] dets={n}{path_note}  speech: "
                  f"{speech if speech else '(silent)'}")

            # Pace to real time so motion/TTC stay realistic.
            elapsed = time.time() - loop_start
            if elapsed < interval:
                time.sleep(interval - elapsed)

        frame_idx += 1

    cap.release()

    # Flush this trial's telemetry file.
    try:
        requests.post(f"{url.rstrip('/')}/telemetry/stop",
                      headers=headers, timeout=10)
    except Exception:  # noqa: BLE001
        pass

    dur = time.time() - t_wall_start
    print(f"\n[DONE] sent {sent} frames in {dur:.1f}s")
    print(f"[DONE] telemetry -> study_logs/{session_id}.jsonl")
    print(f"[NEXT] run: python analyze_study.py study_logs/*.jsonl")


def main():
    p = argparse.ArgumentParser(description="Replay a walking video into the Virtual Eye server.")
    p.add_argument("video", help="path to the recorded video (e.g. eval_videos/hallway.mp4)")
    p.add_argument("--url", default="http://localhost:5000", help="server base URL")
    p.add_argument("--mode", choices=["priority", "naive"], default="priority",
                   help="narration mode to test")
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between sampled frames (default 1.0 = live poll rate)")
    p.add_argument("--session", default=None,
                   help="session_id / log filename (default: <videoname>_<mode>)")
    p.add_argument("--lang", default="en", help="lang code (en|hi|mr)")
    args = p.parse_args()

    session_id = args.session or (
        os.path.splitext(os.path.basename(args.video))[0] + "_" + args.mode
    )
    replay(args.video, args.url, args.mode, args.interval, session_id, args.lang)


if __name__ == "__main__":
    main()
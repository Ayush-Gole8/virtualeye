"""
smoke_test.py — verify the new models load and run BEFORE integrating into server.py.

Place this file in backend/ (next to server.py) with the engine/ folder present.
Run:  python smoke_test.py  path/to/any_test_image.jpg
(or just: python smoke_test.py   -> it will grab one webcam frame)

Expected: prints device, depth timing, a few detections with metric distance + color +
motion, a priority selection, a narrated sentence, and a Florence-2 scene caption.
If this passes, integration into server.py is safe.
"""

import sys
import time
import cv2
import numpy as np

from engine import depth as eng_depth
from engine import color as eng_color
from engine import motion as eng_motion
from engine import priority as eng_priority
from engine import narrate as eng_narrate
from engine import path as eng_path
from engine import ocr as eng_ocr
from engine import vlm as eng_vlm

from ultralytics import YOLO


def get_frame():
    if len(sys.argv) > 1:
        img = cv2.imread(sys.argv[1])
        if img is None:
            raise SystemExit(f"Could not read image: {sys.argv[1]}")
        return img
    # else grab a webcam frame — warm up first so auto-exposure settles
    # (the first few frames are often black/dark and give garbage depth)
    cap = cv2.VideoCapture(0)
    frame = None
    for _ in range(30):
        ok, frame = cap.read()
        if ok:
            time.sleep(0.03)
    cap.release()
    if frame is None:
        raise SystemExit("Could not read from webcam. Pass an image path instead.")
    if float(frame.mean()) < 10.0:
        print("WARNING: webcam frame is almost black (mean < 10). Depth/detection "
              "will be meaningless. Cover nothing, ensure the lens isn't blocked, "
              "or pass a real image: python smoke_test.py test.jpg")
    return frame


def main():
    print("=" * 60)
    print("VIRTUAL EYE 3.0 — ENGINE SMOKE TEST")
    print("=" * 60)

    frame = get_frame()
    h, w = frame.shape[:2]
    print(f"Frame: {w}x{h}")

    # --- YOLO ---
    print("\n[1/5] Loading YOLOv8n...")
    model = YOLO("yolov8n.pt")

    # --- Depth ---
    print("[2/5] Loading Depth Anything V2 (metric indoor small)...")
    eng_depth.load_depth_model(device="cuda")
    t0 = time.time()
    depth_map = eng_depth.compute_depth_map(frame)
    print(f"    depth map shape={depth_map.shape}, "
          f"min={depth_map.min():.2f}m max={depth_map.max():.2f}m, "
          f"time={time.time()-t0:.2f}s")

    # --- Detection + enrichment ---
    print("[3/5] Detection + distance + color...")
    results = model.track(frame, persist=True, conf=0.35)[0]
    dets = []
    if results.boxes is not None:
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls = model.names[int(box.cls[0])]
            tid = int(box.id[0]) if box.id is not None else -1
            cx = (x1 + x2) // 2
            dist = eng_depth.object_distance_from_depth(depth_map, [x1, y1, x2, y2])
            col = eng_color.dominant_color(frame, [x1, y1, x2, y2], cls=cls)
            dets.append({
                "class": cls, "bbox": [x1, y1, x2, y2], "track_id": tid,
                "distance": dist, "distance_str": eng_depth.format_distance(dist),
                "side": ("left" if cx < w*0.33 else "right" if cx > w*0.66 else "center"),
                "cx": cx, "cy": (y1+y2)//2, "color": col,
            })
    dets = eng_motion.update_motion(dets, w)
    for d in dets:
        print(f"    {d['class']:12s} {d['distance_str']:>7s}  {d['side']:6s}  "
              f"color={d['color']}  motion={d['motion']}")

    # --- Priority + narration ---
    print("[4/5] Priority selection + narration...")
    top = eng_priority.prioritize(dets, w, top_k=2, min_score=4.0)
    print(f"    priority picks: {[d['class'] for d in top]}")
    print(f"    NARRATION: \"{eng_narrate.narrate(top)}\"")

    # --- Clear-path navigation ---
    print("[5/8] Clear-path analysis...")
    path_verdict = eng_path.analyze_path(depth_map, w, h)
    print(f"    path clear: {path_verdict['clear']}")
    print(f"    obstacle: {path_verdict.get('obstacle_m', 'N/A')} m")
    print(f"    advice: {path_verdict['advice_str']}")

    # --- Florence-2 scene caption ---
    print("[6/8] Florence-2 scene description...")
    t0 = time.time()
    caption = eng_vlm.describe_scene(frame)
    print(f"    caption ({time.time()-t0:.2f}s): \"{caption}\"")

    # --- OCR text recognition ---
    print("[7/8] OCR text recognition (if any text visible)...")
    t0 = time.time()
    text = eng_ocr.read_text(frame, min_conf=0.25, detail=0)
    print(f"    recognized ({time.time()-t0:.2f}s): \"{text if text else '(no text found)'}\"")

    # --- TTC check (if any approaching object) ---
    print("[8/8] Time-to-collision (TTC) check...")
    approaching = [d for d in dets if d.get("motion") == "approaching" and d.get("ttc")]
    if approaching:
        for d in approaching:
            print(f"    {d['class']} approaching: TTC={d['ttc']:.1f}s, "
                  f"velocity={d['velocity_mps']:.2f} m/s")
    else:
        print("    (no approaching objects)")

    print("\nSMOKE TEST PASSED. All modules loaded and returned data.")


if __name__ == "__main__":
    main()

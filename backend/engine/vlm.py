"""
Vision-Language model for on-demand Q&A and open-vocabulary object finding.

Uses Microsoft Florence-2-base: a single lightweight (0.23B) model that provides
scene captioning ("what's in front of me?") and open-vocabulary detection
("find my water bottle") via task-prompt tokens.

Citation:
Xiao, B., Wu, H., Xu, W., et al. (2024). Florence-2: Advancing a Unified
Representation for a Variety of Vision Tasks. CVPR 2024. arXiv:2311.06242.

Task tokens used:
    <MORE_DETAILED_CAPTION>     -> rich scene description
    <OPEN_VOCABULARY_DETECTION> -> locate an arbitrary named object (returns bboxes)
    <DENSE_REGION_CAPTION>       -> label multiple visible regions for follow-up questions
"""

import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image
import cv2
from unittest.mock import patch as _patch
from transformers.dynamic_module_utils import get_imports as _get_imports

from engine import dialogue as eng_dialogue

_model = None
_processor = None
_device = None


_SUPPORT_RELATIONS = {
    "dining table": "on the table",
    "table": "on the table",
    "desk": "on the desk",
    "bed": "on the bed",
    "chair": "on the chair",
    "couch": "on the couch",
    "bench": "on the bench",
}


def extract_find_target(question):
    """Extract an object phrase from a natural-language locate question."""
    return eng_dialogue.extract_find_target(question)


def infer_support_surface(target_bbox, detections):
    """Infer a cautious support-surface record from overlapping boxes."""
    if not target_bbox:
        return None
    best = None

    for det in detections:
        label = str(det.get("class", "")).lower()
        relation = _SUPPORT_RELATIONS.get(label)
        bbox = det.get("bbox")
        if not relation or not bbox or len(bbox) != 4:
            continue
        if not eng_dialogue.bbox_supported_by(target_bbox, bbox):
            continue
        target_bottom = float(target_bbox[3])
        support_top = float(bbox[1])
        support_height = max(1.0, float(bbox[3]) - support_top)
        score = abs(target_bottom - support_top) / support_height
        if best is None or score < best[0]:
            best = (
                score,
                {
                    "label": eng_dialogue.extract_surface(label) or label,
                    "relation": relation,
                    "bbox": list(map(float, bbox)),
                },
            )

    return best[1] if best else None


def infer_support_relation(target_bbox, detections):
    """Backward-compatible relation-only support inference."""
    support = infer_support_surface(target_bbox, detections)
    return support.get("relation") if support else None


def _fixed_get_imports(filename):
    """
    Florence-2's remote modeling file lists flash_attn as a hard dependency, but
    the model runs correctly without it (it falls back to standard attention).
    flash_attn is very hard to build on Windows, so we strip it from the import
    check for the Florence modeling file only, leaving every other check intact.
    """
    imports = _get_imports(filename)
    if str(filename).endswith("modeling_florence2.py") and "flash_attn" in imports:
        imports.remove("flash_attn")
    return imports


def load_vlm(device="cuda"):
    """Load Florence-2-base once into globals."""
    global _model, _processor, _device
    if _model is None:
        print("[VLM] Loading Florence-2-base...")
        _device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
        dtype = torch.float16 if _device == "cuda" else torch.float32
        with _patch("transformers.dynamic_module_utils.get_imports", _fixed_get_imports):
            _model = AutoModelForCausalLM.from_pretrained(
                "microsoft/Florence-2-base",
                trust_remote_code=True,
                torch_dtype=dtype,
            ).to(_device).eval()
            _processor = AutoProcessor.from_pretrained(
                "microsoft/Florence-2-base",
                trust_remote_code=True,
            )
        print(f"[VLM] Loaded on {_device}")
    return _model, _processor, _device


def _run(frame_bgr, task_prompt, text_input=None, max_new_tokens=256):
    """
    Core Florence-2 inference. Returns the parsed dict from post_process_generation.
    """
    model, processor, device = load_vlm()
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    prompt = task_prompt if text_input is None else task_prompt + text_input
    inputs = processor(text=prompt, images=img, return_tensors="pt").to(device)

    # Match model dtype for pixel_values
    if device == "cuda":
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.float16)

    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=max_new_tokens,
            num_beams=3,
            do_sample=False,
        )

    generated_text = processor.batch_decode(
        generated_ids, skip_special_tokens=False
    )[0]

    parsed = processor.post_process_generation(
        generated_text,
        task=task_prompt,
        image_size=(img.width, img.height),
    )
    return parsed


def describe_scene(frame_bgr):
    """
    'What's in front of me?' -> a detailed natural-language scene caption.

    Returns:
        caption string
    """
    result = _run(frame_bgr, "<MORE_DETAILED_CAPTION>")
    return result.get("<MORE_DETAILED_CAPTION>", "I could not describe the scene.")


def dense_region_captions(frame_bgr):
    """Return labeled Florence-2 regions for relational scene follow-ups."""
    task = "<DENSE_REGION_CAPTION>"
    result = _run(frame_bgr, task, max_new_tokens=512)
    payload = result.get(task, {})
    bboxes = payload.get("bboxes", [])
    labels = payload.get("labels") or payload.get("bboxes_labels") or []
    regions = []
    for bbox, label in zip(bboxes, labels):
        if not bbox or len(bbox) != 4:
            continue
        regions.append({
            "label": eng_dialogue.canonical_label(label),
            "bbox": list(map(float, bbox)),
            "source": "florence_dense",
        })
    return eng_dialogue.dedupe_scene_items(regions)


def find_object(frame_bgr, target):
    """
    'Find my <target>' -> locate an object by open-vocabulary detection.

    Args:
        frame_bgr: BGR frame
        target: object name string, e.g. "water bottle"

    Returns:
        dict {found: bool, bbox: [x1,y1,x2,y2] or None, cx: int or None}
        Returns the largest matching box (closest / most prominent).
    """
    task = "<OPEN_VOCABULARY_DETECTION>"
    result = _run(frame_bgr, task, text_input=target)

    # Florence returns {'<OPEN_VOCABULARY_DETECTION>': {'bboxes': [...], ...}}
    payload = result.get(task, {})
    bboxes = payload.get("bboxes", [])
    labels = payload.get("labels") or payload.get("bboxes_labels") or []

    if not bboxes:
        return {"found": False, "bbox": None, "cx": None, "label": None}

    # Choose the largest box (usually the closest instance)
    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    best_index, best = max(enumerate(bboxes), key=lambda pair: area(pair[1]))
    x1, y1, x2, y2 = map(int, best)
    cx = (x1 + x2) // 2

    label = labels[best_index] if best_index < len(labels) else target
    return {
        "found": True,
        "bbox": [x1, y1, x2, y2],
        "cx": cx,
        "label": eng_dialogue.canonical_label(label),
    }

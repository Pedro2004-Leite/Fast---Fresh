"""Turning raw predictions into the files a client downloads.  CPU-only."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from conceptseg.scoring import filter_by_area, mask_nms, top_scored_predictions

RESULT_FILE = "result.json"
MASKS_FILE = "masks.npz"


def finalize_predictions(predictions: list[dict], frame_hw: tuple[int, int], params: dict) -> list[dict]:
    """Area floor, exact-mask NMS, then keep the best ``max_predictions``.

    ``predictions`` are in original-frame coordinates, each with a ``box`` and a
    box-cropped boolean ``mask``.  No upper area bound: a generic service must not
    assume what size of thing a caller is looking for.
    """
    kept = filter_by_area(predictions, frame_hw, params["min_area"], 1.0)
    kept = mask_nms(kept, params["nms_iou"])
    return top_scored_predictions(kept, params["max_predictions"] or None)


def write_result(job_dir: Path, job_id: str, frame_hw: tuple[int, int], predictions: list[dict],
                 params: dict, timings: dict) -> dict:
    """Write ``result.json`` (metadata) and ``masks.npz`` (one cropped mask per prediction)."""
    height, width = frame_hw
    arrays = {"image_width": np.int32(width), "image_height": np.int32(height)}
    records = []
    for index, prediction in enumerate(predictions):
        arrays[f"mask_{index}"] = prediction["mask"]
        arrays[f"box_{index}"] = np.asarray(prediction["box"], dtype=np.int32)
        records.append({
            "index": index,
            "score": round(float(prediction["score"]), 5),
            "class_probability": round(float(prediction.get("class_probability", 0.0)), 5),
            "presence_probability": round(float(prediction.get("presence_probability", 0.0)), 5),
            "box_xyxy": [int(v) for v in prediction["box"]],
            "area_px": int(prediction.get("mask_area", prediction["mask"].sum())),
        })
    np.savez_compressed(job_dir / MASKS_FILE, **arrays)
    result = {
        "job_id": job_id,
        "image": {"width": int(width), "height": int(height)},
        "params": params,
        "n_predictions": len(records),
        "predictions": records,
        "timings_s": {k: round(v, 4) for k, v in timings.items()},
        "masks_file": MASKS_FILE,
        "masks_layout": "masks.npz: mask_<i> = boolean crop of prediction i, box_<i> = [x0,y0,x1,y1] "
                        "of that crop in the original image; also image_width, image_height.",
    }
    (job_dir / RESULT_FILE).write_text(json.dumps(result, indent=2))
    return result

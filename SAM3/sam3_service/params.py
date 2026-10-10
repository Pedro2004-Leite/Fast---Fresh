"""Request parameters: validated plain dicts, so workers need no web framework."""
from __future__ import annotations

SCORE_MODES = ("joint", "class", "presence")
POLARITIES = ("positive", "negative")

DEFAULTS = {
    "text": None,
    "threshold": 0.30,
    "score_mode": "joint",
    "nms_iou": 0.60,
    "min_area": 25,
    "max_predictions": 100,
    "exemplars": [],
    "gpu": None,
}


def parse_params(raw: dict, upload_names: set[str]) -> dict:
    """Validate a request's ``params`` object.  Raises ValueError with a readable reason.

    ``upload_names`` are the file fields that arrived with the request; every
    exemplar must name one of them.
    """
    if not isinstance(raw, dict):
        raise ValueError("params must be a JSON object")
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params: {sorted(unknown)}")
    params = {**DEFAULTS, **raw}

    text = params["text"]
    if text is not None:
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        text = text.strip() or None
    params["text"] = text

    for key, low, high in (("threshold", 0.0, 1.0), ("nms_iou", 0.0, 1.0)):
        value = params[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not low <= value <= high:
            raise ValueError(f"{key} must be a number in [{low}, {high}]")
        params[key] = float(value)
    for key in ("min_area", "max_predictions"):
        value = params[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    gpu = params["gpu"]
    if gpu is not None and (not isinstance(gpu, int) or isinstance(gpu, bool) or gpu < 0):
        raise ValueError("gpu must be a non-negative integer (torch CUDA index) or null")
    if params["score_mode"] not in SCORE_MODES:
        raise ValueError(f"score_mode must be one of {SCORE_MODES}")

    exemplars = params["exemplars"]
    if not isinstance(exemplars, list):
        raise ValueError("exemplars must be a list")
    clean = []
    for i, exemplar in enumerate(exemplars):
        where = f"exemplars[{i}]"
        if not isinstance(exemplar, dict) or set(exemplar) - {"file", "boxes"}:
            raise ValueError(f"{where} must be an object with 'file' and 'boxes'")
        if exemplar.get("file") not in upload_names:
            raise ValueError(f"{where}.file {exemplar.get('file')!r} was not uploaded as a file field")
        boxes = exemplar.get("boxes")
        if not isinstance(boxes, list) or not boxes:
            raise ValueError(f"{where}.boxes must be a non-empty list")
        clean_boxes = []
        for j, entry in enumerate(boxes):
            box = entry.get("box") if isinstance(entry, dict) else None
            polarity = entry.get("polarity", "positive") if isinstance(entry, dict) else None
            ok = (isinstance(box, list) and len(box) == 4
                  and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box))
            if not ok or box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError(f"{where}.boxes[{j}].box must be [x0, y0, x1, y1] with x1>x0, y1>y0")
            if polarity not in POLARITIES:
                raise ValueError(f"{where}.boxes[{j}].polarity must be one of {POLARITIES}")
            clean_boxes.append({"box": [float(v) for v in box], "polarity": polarity})
        clean.append({"file": exemplar["file"], "boxes": clean_boxes})
    params["exemplars"] = clean

    if params["text"] is None and not clean:
        raise ValueError("need a text prompt, at least one exemplar, or both")
    return params

"""Client for the SAM 3 web service: one function, :func:`sam3`.

    from sam3_client import sam3

    preds = sam3("photo.jpg", text_prompt="light rock")
    preds = sam3("photo.jpg", example_image="ref.jpg",
                 bounding_box_exemplar=[[100, 200, 900, 700]],
                 bounding_box_counter=[[100, 200, 800, 600]])
    preds = sam3("photo.jpg", "light rock", "ref.jpg", [[100, 200, 900, 700]], GPU=0)

This file is deliberately standalone (it imports nothing else from this repo)
so it can be copied next to a notebook as-is.  It needs ``requests`` and
``numpy``; Pillow is only needed if you pass a PIL image or an array.

Where the server is, in order of precedence: ``server=`` on the call,
``sam3_host(url)``, the ``SAM3_SERVICE_URL`` environment variable, then
``http://127.0.0.1:8000``.

    from sam3_client import sam3, sam3_host
    sam3_host("gpu-box.lab:8000")
"""
from __future__ import annotations

import io
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_URL = "http://127.0.0.1:8000"
_host: str | None = None


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        raise ValueError("the server URL is empty")
    return url if "://" in url else f"http://{url}"


def sam3_host(url: str | None = None) -> str:
    """Set where the SAM 3 service is, for every later :func:`sam3` call.

    ``url`` may omit the scheme (``"gpu-box.lab:8000"`` becomes
    ``"http://gpu-box.lab:8000"``).  ``sam3_host(None)`` forgets the setting and
    goes back to ``$SAM3_SERVICE_URL`` / the default.  Returns the address now in
    effect.  Nothing is contacted here; a wrong address shows up on the next call.
    """
    global _host
    _host = None if url is None else _normalize_url(url)
    return _server_url()


def _server_url(server: str | None = None) -> str:
    if server:
        return _normalize_url(server)
    return _host or _normalize_url(os.environ.get("SAM3_SERVICE_URL") or DEFAULT_URL)


class Sam3Error(RuntimeError):
    """The service refused the request, or the job failed."""


@dataclass
class Prediction:
    """One segmented object.

    ``mask`` is the boolean crop inside ``box`` only (cheap to transfer);
    ``box`` is ``(x0, y0, x1, y1)`` in target-image pixels, so ``(x0, y0)`` is
    where the crop sits.  Use :meth:`full_mask` for a frame-sized mask.
    """

    score: float
    box: tuple[int, int, int, int]
    mask: np.ndarray
    area: int
    class_probability: float
    presence_probability: float
    image_hw: tuple[int, int]

    def full_mask(self) -> np.ndarray:
        """The mask as a (height, width) boolean array for the whole target image."""
        out = np.zeros(self.image_hw, dtype=bool)
        x0, y0, x1, y1 = self.box
        out[y0:y1, x0:x1] = self.mask
        return out


def _image_bytes(image) -> bytes:
    """A path, raw encoded bytes, a PIL image or an (H, W[, 3]) array -> file bytes."""
    if isinstance(image, (str, os.PathLike)):
        return Path(image).read_bytes()
    if isinstance(image, (bytes, bytearray)):
        return bytes(image)
    from PIL import Image

    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    if not isinstance(image, Image.Image):
        raise TypeError(f"cannot use a {type(image).__name__} as an image")
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "PNG")
    return buffer.getvalue()


def _boxes(boxes, polarity: str, name: str) -> list[dict]:
    """A list of ``[x0, y0, x1, y1]`` -> the service's box entries.

    A single flat box ``[x0, y0, x1, y1]`` is accepted as a list of one.
    """
    if boxes is None:
        return []
    boxes = list(boxes)
    if len(boxes) == 4 and all(isinstance(v, (int, float, np.integer, np.floating)) for v in boxes):
        boxes = [boxes]
    entries = []
    for box in boxes:
        box = [float(v) for v in box]
        if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError(f"{name}: each box must be [x0, y0, x1, y1] with x1 > x0 and y1 > y0, got {box}")
        entries.append({"box": box, "polarity": polarity})
    return entries


def sam3(target_image, text_prompt=None, example_image=None, bounding_box_exemplar=None,
         bounding_box_counter=None, GPU=None,
         *, threshold: float = 0.30, server: str | None = None, timeout: float = 600.0,
         poll_interval: float = 0.1, **options) -> list[Prediction]:
    """Segment ``target_image`` with the SAM 3 service; returns predictions, best score first.

    Parameters
    ----------
    target_image
        Required.  A file path, a PIL image, a numpy array or encoded bytes.
    text_prompt
        Optional text, e.g. ``"light rock"``.
    example_image
        Optional reference image to learn from; needs at least one box below.
    bounding_box_exemplar
        Boxes on ``example_image`` around what you WANT: a list of
        ``[x0, y0, x1, y1]`` in the example image's pixels.
    bounding_box_counter
        Boxes on ``example_image`` around what you do NOT want (counter-examples),
        same format.  Optional; may be combined with the exemplar boxes.
    GPU
        Optional torch CUDA index to pin the job to.  ``None`` lets the service
        pick whichever GPU is free.
    threshold
        Minimum score of a returned object.
    server
        Address for this call only; otherwise :func:`sam3_host`, then
        ``$SAM3_SERVICE_URL``, then ``http://127.0.0.1:8000``.
    **options
        Passed to the service unchanged: ``nms_iou``, ``min_area``,
        ``max_predictions``, ``score_mode``.

    At least one of ``text_prompt`` or ``example_image`` is needed; with both,
    the text and the visual example are combined in one prompt.  Exemplar and
    counter boxes are joined into a single visual prompt, as in the repo's
    positive/negative setup.
    """
    import requests

    if text_prompt is None and example_image is None:
        raise ValueError("give a text_prompt, an example_image (with bounding_box_exemplar), or both")
    positive = _boxes(bounding_box_exemplar, "positive", "bounding_box_exemplar")
    negative = _boxes(bounding_box_counter, "negative", "bounding_box_counter")
    if example_image is None and (positive or negative):
        raise ValueError("bounding_box_exemplar / bounding_box_counter need an example_image to refer to")
    if example_image is not None and not (positive or negative):
        raise ValueError("example_image needs bounding_box_exemplar and/or bounding_box_counter")

    params: dict = {"threshold": threshold, "gpu": GPU, **options}
    if text_prompt is not None:
        params["text"] = text_prompt
    files = {"image": ("target", _image_bytes(target_image))}
    if example_image is not None:
        params["exemplars"] = [{"file": "example", "boxes": positive + negative}]
        files["example"] = ("example", _image_bytes(example_image))

    base = _server_url(server)
    try:
        response = requests.post(f"{base}/jobs", data={"params": json.dumps(params)}, files=files)
    except requests.ConnectionError as exc:
        raise Sam3Error(f"cannot reach the SAM 3 service at {base}: {exc}") from None
    if response.status_code != 202:
        raise Sam3Error(f"service rejected the request ({response.status_code}): {_detail(response)}")
    job_id = response.json()["job_id"]

    deadline = time.monotonic() + timeout
    while True:
        body = requests.get(f"{base}/jobs/{job_id}").json()
        if body["state"] == "done":
            break
        if body["state"] == "failed":
            raise Sam3Error(f"job {job_id} failed on the service:\n{body.get('error', '')}")
        if time.monotonic() > deadline:
            raise Sam3Error(f"job {job_id} did not finish within {timeout:g} s (state: {body['state']})")
        time.sleep(poll_interval)

    result = body["result"]
    if not result["predictions"]:
        return []
    masks = np.load(io.BytesIO(requests.get(f"{base}/jobs/{job_id}/masks").content))
    hw = (result["image"]["height"], result["image"]["width"])
    return [
        Prediction(
            score=p["score"], box=tuple(p["box_xyxy"]), mask=masks[f"mask_{p['index']}"], area=p["area_px"],
            class_probability=p["class_probability"], presence_probability=p["presence_probability"],
            image_hw=hw,
        )
        for p in result["predictions"]
    ]


def _detail(response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text

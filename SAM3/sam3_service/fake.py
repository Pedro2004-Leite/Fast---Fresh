"""A model-free engine with the same interface as :class:`Sam3Engine`.

For exercising the queue, scheduler and HTTP layer on a machine with no GPU or
checkpoint (``--engine fake``, and the tests).  It returns one centred
rectangle per job and says so in its scores: it is plumbing, not segmentation.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .engine import Prepared, load_rgb
from .results import finalize_predictions, write_result


class FakeEngine:
    def __init__(self, checkpoint=None, device_index: int = 0, image_size: int = 1024, delay_s: float = 0.0):
        self.device_index = device_index
        self.delay_s = float(delay_s)

    def load(self) -> None:
        pass

    def preload(self, job: dict) -> Prepared:
        started = time.perf_counter()
        rgb = load_rgb(Path(job["image_path"]))
        return Prepared(rgb, None, {}, rgb.shape[:2], time.perf_counter() - started)

    def infer(self, job: dict, prepared: Prepared) -> list[dict]:
        if job["params"]["text"] == "__fail__":
            raise RuntimeError("requested failure")
        time.sleep(self.delay_s)
        height, width = prepared.frame_hw
        x0, y0, x1, y1 = width // 4, height // 4, 3 * width // 4, 3 * height // 4
        return [{"score": 0.5, "box": [x0, y0, x1, y1], "mask": np.ones((y1 - y0, x1 - x0), dtype=bool),
                 "class_probability": 0.5, "presence_probability": 1.0}]

    def postprocess(self, job: dict, prepared: Prepared, raw: list[dict], gpu_s: float) -> dict:
        kept = finalize_predictions(raw, prepared.frame_hw, job["params"])
        timings = {"load": prepared.load_s, "gpu": gpu_s, "post": 0.0}
        return write_result(Path(job["dir"]), job["job_id"], prepared.frame_hw, kept, job["params"], timings)

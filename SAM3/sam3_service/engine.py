"""The SAM 3 engine: model resident on one GPU, split into three pipeline stages.

``preload``      CPU thread  -- decode, resize, async host->device copy
``infer``        GPU thread  -- the only caller of the model
``postprocess``  CPU thread  -- masks back to the original frame, NMS, files

Everything algorithmic is reused from :mod:`conceptseg.sam3`; this module only
sequences it.  One model has one global text state (``model.set_classes``), which
is why exactly one thread may call ``infer`` per engine.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .results import finalize_predictions, write_result

POLARITY_LABEL = {"positive": 1, "negative": 0}


def load_rgb(path: Path) -> np.ndarray:
    """Decode an upload to RGB, honouring EXIF orientation (as the vein stage does)."""
    return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


@dataclass
class Prepared:
    """What the loader hands to the GPU thread."""

    tensor: object          # uint8 [1,3,S,S] on the GPU, copied on the side stream
    event: object           # CUDA event recorded after that copy
    mapping: dict           # square-canvas -> original-frame mapping
    frame_hw: tuple[int, int]
    load_s: float


class Sam3Engine:
    def __init__(self, checkpoint: str | Path, device_index: int, image_size: int = 1024,
                 exemplar_cache: int = 64):
        self.checkpoint = Path(checkpoint)
        self.device_index = int(device_index)
        self.image_size = int(image_size)
        self.exemplar_cache = exemplar_cache
        self._tokens: OrderedDict[str, tuple] = OrderedDict()

    # -- lifecycle -------------------------------------------------------------------
    def load(self) -> None:
        import torch

        from conceptseg.sam3.predictor import build_predictor, torch_device

        if not self.checkpoint.exists():
            raise FileNotFoundError(f"SAM 3 checkpoint not found: {self.checkpoint}")
        torch.cuda.set_device(self.device_index)
        self.device = torch_device(str(self.device_index))
        self.predictor = build_predictor(self.checkpoint, str(self.device_index), self.image_size)
        self.model = self.predictor.model
        # Use the size the predictor actually settled on, not the one we asked for.
        self.image_size = int(self.predictor.imgsz[0])
        self.copy_stream = torch.cuda.Stream(device=self.device)

    # -- stage 1: CPU thread -----------------------------------------------------------
    def preload(self, job: dict) -> Prepared:
        import torch

        from conceptseg.sam3.visual_tokens import resize_to_square

        started = time.perf_counter()
        rgb = load_rgb(Path(job["image_path"]))
        square, mapping = resize_to_square(rgb, self.image_size)
        host = torch.from_numpy(np.ascontiguousarray(square.transpose(2, 0, 1)))[None].pin_memory()
        with torch.cuda.stream(self.copy_stream):
            tensor = host.to(self.device, non_blocking=True)
            event = torch.cuda.Event()
            event.record(self.copy_stream)
        return Prepared(tensor, event, mapping, rgb.shape[:2], time.perf_counter() - started)

    # -- stage 2: the GPU thread ---------------------------------------------------------
    def infer(self, job: dict, prepared: Prepared) -> list[dict]:
        import torch

        from conceptseg.sam3 import collect_predictions
        from conceptseg.sam3.prompting import (
            forward_text_and_visual, forward_text_only, forward_visual_only, prepare_text_prompt,
        )

        params = job["params"]
        stream = torch.cuda.current_stream()
        stream.wait_event(prepared.event)
        prepared.tensor.record_stream(stream)

        # Same arithmetic as predictor.preprocess() does after its own host->device copy.
        image = (prepared.tensor - self.predictor.mean) / self.predictor.std
        image = image.half() if self.model.fp16 else image.float()
        with torch.no_grad():
            raw = self.model.backbone.forward_image(image)
            tokens = mask = None
            if params["exemplars"]:
                tokens, mask = self._exemplar_prompt(job)
            if params["text"] is not None:
                prepare_text_prompt(self.model, params["text"])
            if tokens is not None and params["text"] is not None:
                out = forward_text_and_visual(self.model, raw, tokens, mask)
            elif tokens is not None:
                out = forward_visual_only(self.model, raw, tokens, mask)
            else:
                out = forward_text_only(self.model, raw)
            return collect_predictions(
                out, self.image_size, params["threshold"], "service", params["score_mode"]
            )

    def _exemplar_prompt(self, job: dict):
        """Encode (or fetch from cache) the visual tokens for a job's exemplars.

        Tokens depend only on the reference image bytes and its boxes, so a
        caller who keeps sending the same reference pays the encoder once.
        """
        from conceptseg.sam3.visual_tokens import compose_prompt, encode_visual_reference

        entries = []
        for exemplar in job["params"]["exemplars"]:
            path = Path(job["exemplar_paths"][exemplar["file"]])
            key = hashlib.sha256(path.read_bytes() + json.dumps(exemplar["boxes"]).encode()).hexdigest()
            if key in self._tokens:
                self._tokens.move_to_end(key)
            else:
                rgb = load_rgb(path)
                height, width = rgb.shape[:2]
                encoded = []
                for item in exemplar["boxes"]:
                    x0, y0, x1, y1 = item["box"]
                    box = [max(0.0, x0), max(0.0, y0), min(float(width), x1), min(float(height), y1)]
                    if box[2] <= box[0] or box[3] <= box[1]:
                        raise ValueError(f"box {item['box']} lies outside {exemplar['file']} ({width}x{height})")
                    tokens, masks, _ = encode_visual_reference(
                        self.model, self.predictor, rgb, box, self.device,
                        label=POLARITY_LABEL[item["polarity"]],
                    )
                    encoded.append({"tokens": tokens, "masks": masks})
                self._tokens[key] = encoded
                while len(self._tokens) > self.exemplar_cache:
                    self._tokens.popitem(last=False)
            entries.extend(self._tokens[key])
        tokens, mask = compose_prompt(entries, "box_only")
        return tokens.to(self.device), mask.to(self.device)

    # -- stage 3: CPU thread -------------------------------------------------------------
    def postprocess(self, job: dict, prepared: Prepared, raw_predictions: list[dict], gpu_s: float) -> dict:
        from conceptseg.sam3.visual_tokens import restore_square_predictions

        started = time.perf_counter()
        restored = restore_square_predictions(raw_predictions, prepared.mapping)
        kept = finalize_predictions(restored, prepared.frame_hw, job["params"])
        timings = {"load": prepared.load_s, "gpu": gpu_s, "post": time.perf_counter() - started}
        return write_result(Path(job["dir"]), job["job_id"], prepared.frame_hw, kept, job["params"], timings)

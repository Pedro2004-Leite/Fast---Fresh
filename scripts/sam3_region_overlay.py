"""Run every classes.json text prompt on one full frame and colour the masks by region.

Masks that are near one another (within ``--gap`` px) form a region.  Exactly one region is
drawn red (``--red``: the lowest mean score by default, or ``center`` for the one nearest the image centre), every other region green.

    python scripts/sam3_region_overlay.py dataset/train/6376/1751009380.jpg --server localhost:8001

The service's input size is fixed at start-up, so for more than 350 px start one with
``python -m sam3_service --port 8001 --image-size 1260``.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SAM3"))
from sam3_client import sam3  # noqa: E402

GREEN, RED = (40, 200, 70), (230, 30, 40)


def dedupe(items: list[dict], iou_thr: float) -> list[dict]:
    """Greedy NMS across prompts (the same fruit is often found by several prompts)."""
    keep: list[dict] = []
    for it in sorted(items, key=lambda d: -d["score"]):
        if all((it["mask"] & k["mask"]).sum() / max((it["mask"] | k["mask"]).sum(), 1) < iou_thr for k in keep):
            keep.append(it)
    return keep


def regions(items: list[dict], gap: int) -> list[list[int]]:
    """Connected groups of masks whose dilation by gap/2 px touches."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap | 1, gap | 1))
    grown = [cv2.dilate(it["mask"].astype(np.uint8), k).astype(bool) for it in items]
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if (grown[i] & grown[j]).any():
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--server", default="localhost:8001")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--gap", type=int, default=40, help="masks closer than this many px share a region")
    ap.add_argument("--nms-iou", type=float, default=0.6)
    ap.add_argument("--red", choices=["lowest-score", "smallest", "largest", "center"], default="lowest-score")
    ap.add_argument("--red-prompt", default=None, help="extra text prompt drawn red; every classes.json mask is green")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    prompts = [c["sam3_prompt"] for c in json.loads((ROOT / "classes.json").read_text())]

    def run(p: str):
        return p, sam3(args.image, text_prompt=p, threshold=args.threshold, server=args.server)

    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for p, preds in pool.map(run, prompts):
            print(f"{p:<28} {len(preds)}")
            items += [{"prompt": p, "score": q.score, "mask": q.full_mask()} for q in preds]
    items = dedupe(items, args.nms_iou)
    red_items: list[dict] = []
    if args.red_prompt:
        preds = sam3(args.image, text_prompt=args.red_prompt, threshold=args.threshold, server=args.server)
        print(f"{args.red_prompt:<28} {len(preds)}  (red)")
        red_items = dedupe([{"prompt": args.red_prompt, "score": q.score, "mask": q.full_mask()} for q in preds], args.nms_iou)
    print(f"{len(items)} masks after cross-prompt NMS")
    if not items:
        sys.exit("no masks found")

    groups = regions(items, args.gap)
    h, w = items[0]["mask"].shape

    def centre_dist(mask: np.ndarray) -> float:
        ys, xs = np.nonzero(mask)
        return float(np.hypot(xs.mean() - w / 2, ys.mean() - h / 2))

    key = {
        "lowest-score": lambda g: np.mean([items[i]["score"] for i in g]),
        "smallest": lambda g: sum(items[i]["mask"].sum() for i in g),
        "largest": lambda g: -sum(items[i]["mask"].sum() for i in g),
        "center": lambda g: min(centre_dist(items[i]["mask"]) for i in g),
    }[args.red]
    red = [] if args.red_prompt else min(groups, key=key)

    img = np.asarray(Image.open(args.image).convert("RGB")).astype(np.float32)
    for g in groups:
        col = np.array(RED if g is red and not args.red_prompt else GREEN, dtype=np.float32)
        union = np.zeros(img.shape[:2], bool)
        for i in g:
            union |= items[i]["mask"]
        img[union] = 0.45 * img[union] + 0.55 * col
        cnts, _ = cv2.findContours(union.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, cnts, -1, col.tolist(), 2)
    for it in red_items:
        col = np.array(RED, dtype=np.float32)
        img[it["mask"]] = 0.45 * img[it["mask"]] + 0.55 * col
        cnts, _ = cv2.findContours(it["mask"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, cnts, -1, col.tolist(), 2)
    out = args.out or ROOT / "overlay" / "sam3_regions" / f"{args.image.parent.name}_{args.image.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img.clip(0, 255).astype(np.uint8)).save(out)
    if args.red_prompt:
        print(f"{len(groups)} green regions, {len(red_items)} red '{args.red_prompt}' masks\n{out}")
        return
    names = sorted({items[i]["prompt"] for i in red})
    print(f"{len(groups)} regions, 1 red ({len(red)} masks: {', '.join(names)})\n{out}")


if __name__ == "__main__":
    main()

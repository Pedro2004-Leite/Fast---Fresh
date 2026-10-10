"""Segment the crops in output/crops with SAM 3 using only the text prompt.

The prompt of each crop is ``sam3_prompt`` of its class in output/crops/classes.json.
Overlays go to overlay/sam3_textonly_plural/<class_key>/<image>.png
(or overlay/sam3_textonly_singular with --singular, which prompts with the singular name).

    python scripts/sam3_textonly.py --limit 10          # 10 images, spread over classes
    python scripts/sam3_textonly.py                     # everything (skips finished overlays)

At most ``--max-queue`` jobs (default 5) are ever submitted to the server at once.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SAM3"))
from sam3_client import Sam3Error, sam3  # noqa: E402

CROPS = ROOT / "output" / "crops"
SINGULAR = ROOT / "dataset" / "classes_singular.json"
PALETTE = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48),
           (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212)]


def pick(rows: list[dict], limit: int | None) -> list[dict]:
    """First ``limit`` rows taking one per class_key in turn, so classes are varied."""
    if limit is None:
        return rows
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(r["class_key"], []).append(r)
    order = itertools.zip_longest(*by_class.values())
    return list(itertools.islice((r for grp in order for r in grp if r), limit))


def draw_overlay(image_path: Path, preds, prompt: str, out_path: Path) -> None:
    img = Image.open(image_path).convert("RGB")
    base = np.asarray(img).astype(np.float32)
    for i, p in enumerate(preds):
        m = p.full_mask()
        col = np.array(PALETTE[i % len(PALETTE)], dtype=np.float32)
        base[m] = 0.5 * base[m] + 0.5 * col
    img = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(img)
    for i, p in enumerate(preds):
        col = PALETTE[i % len(PALETTE)]
        d.rectangle(p.box, outline=col, width=2)
        d.text((p.box[0] + 3, p.box[1] + 2), f"{p.score:.2f}", fill=col)
    d.text((4, 4), f'"{prompt}": {len(preds)}', fill=(255, 255, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="only this many images (varied classes)")
    ap.add_argument("--max-queue", type=int, default=5, help="max jobs in flight at the server")
    ap.add_argument("--singular", action="store_true", help="prompt with the singular class name")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--server", default=None)
    ap.add_argument("--gpu", type=int, default=None, help="pin jobs to this CUDA index (default: any free)")
    args = ap.parse_args()

    prompts = {c["class_key"]: c["sam3_prompt"] for c in json.loads((CROPS / "classes.json").read_text())}
    rows = [json.loads(line) for line in (CROPS / "dataset.jsonl").read_text().splitlines() if line.strip()]
    rows = pick(rows, args.limit)
    out_root = ROOT / "overlay" / ("sam3_textonly_singular" if args.singular else "sam3_textonly_plural")
    if args.singular:
        # singular name per class_key, matched through product ids (classes_singular.json: name -> ids)
        pid2name = {pid: name for name, pids in json.loads(SINGULAR.read_text()).items() for pid in pids}
        for r in (json.loads(l) for l in (CROPS / "dataset.jsonl").read_text().splitlines() if l.strip()):
            prompts[r["class_key"]] = pid2name[r["product_id"]]

    def run(row: dict):
        src = CROPS / row["image"]
        out = out_root / row["class_key"] / (src.stem + ".png")
        prompt = prompts[row["class_key"]]
        preds = sam3(src, text_prompt=prompt, threshold=args.threshold, server=args.server, GPU=args.gpu)
        draw_overlay(src, preds, prompt, out)
        return row, prompt, preds, out

    todo = [r for r in rows if not (out_root / r["class_key"] / (Path(r["image"]).stem + ".png")).exists()]
    print(f"{len(rows)} selected, {len(todo)} to do, {args.max_queue} in flight at most")
    t0, done, failed = time.time(), 0, 0
    # A pool of max_queue threads, each blocking on its own job: never more than max_queue queued/running.
    with ThreadPoolExecutor(max_workers=args.max_queue) as pool:
        futs = {pool.submit(run, r): r for r in todo}
        for f in as_completed(futs):
            row = futs[f]
            try:
                _, prompt, preds, out = f.result()
                done += 1
                best = f"{preds[0].score:.2f}" if preds else "-"
                print(f"[{done + failed}/{len(todo)}] {row['class_key']:<24} n={len(preds):<3} best={best}  {out.relative_to(ROOT)}")
            except (Sam3Error, OSError) as exc:
                failed += 1
                print(f"[{done + failed}/{len(todo)}] FAILED {row['image']}: {exc}", file=sys.stderr)
    print(f"done={done} failed={failed} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

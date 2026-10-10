"""Segment the crops in output/crops with SAM 3 using a visual example, in three modes.

The visual example and the text prompt of each product_id are its entry in
output/crops/examples_by_product.json (made by scripts/pick_examples.py): a box on another
crop of that product, plus the prompt. Products without a box are skipped.

    visual       only the example box
    text_visual  the product's prompt (e.g. "packaged apples") + example box
    text_nopack  text prompt without the word "packaged" (e.g. "apples") + example box
                 (only run for prompts that start with "packaged ")

Overlays go to overlay/sam3_visual/<mode>/<product_id>/<image>.png

    python scripts/sam3_visual.py --limit 10            # 10 images, spread over classes
    python scripts/sam3_visual.py --modes visual        # one mode only
    python scripts/sam3_visual.py                       # everything (skips finished overlays)

The crop used as the example is never segmented itself. At most ``--max-queue`` jobs
(default 5) are ever submitted to the server at once.
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
MODES = ("visual", "text_visual", "text_nopack")
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


def draw_overlay(image_path: Path, preds, label: str, out_path: Path) -> None:
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
    d.text((4, 4), f"{label}: {len(preds)}", fill=(255, 255, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="only this many images (varied classes)")
    ap.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    ap.add_argument("--max-queue", type=int, default=5, help="max jobs in flight at the server")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--server", default=None)
    ap.add_argument("--gpu", type=int, default=None, help="pin jobs to this CUDA index (default: any free)")
    args = ap.parse_args()

    examples = {pid: ex for pid, ex in json.loads((CROPS / "examples_by_product.json").read_text()).items()
                if ex.get("box") and ex.get("image") and ex.get("prompt")}
    rows = [json.loads(line) for line in (CROPS / "dataset.jsonl").read_text().splitlines() if line.strip()]
    rows = [r for r in rows
            if str(r["product_id"]) in examples
            and r["image"] != examples[str(r["product_id"])]["image"]]
    rows = pick(rows, args.limit)
    out_root = ROOT / "overlay" / "sam3_visual"

    def text_for(mode: str, product_id: str) -> str | None:
        if mode == "visual":
            return None
        prompt = examples[product_id]["prompt"]
        return prompt.replace("packaged ", "", 1) if mode == "text_nopack" else prompt

    def out_path(mode: str, row: dict) -> Path:
        return out_root / mode / str(row["product_id"]) / (Path(row["image"]).stem + ".png")

    def run(mode: str, row: dict):
        src = CROPS / row["image"]
        ex = examples[str(row["product_id"])]
        text = text_for(mode, str(row["product_id"]))
        preds = sam3(src, text_prompt=text, example_image=CROPS / ex["image"],
                     bounding_box_exemplar=[ex["box"]], threshold=args.threshold,
                     server=args.server, GPU=args.gpu)
        out = out_path(mode, row)
        draw_overlay(src, preds, f"{mode} [{text or '-'}]", out)
        return preds, out

    # text_nopack only differs from text_visual when the prompt starts with "packaged "
    todo = [(m, r) for r in rows for m in args.modes if not out_path(m, r).exists()
            and not (m == "text_nopack" and not examples[str(r["product_id"])]["prompt"].startswith("packaged "))]
    print(f"{len(rows)} images x {len(args.modes)} modes, {len(todo)} to do, {args.max_queue} in flight at most")
    t0, done, failed = time.time(), 0, 0
    # A pool of max_queue threads, each blocking on its own job: never more than max_queue queued/running.
    with ThreadPoolExecutor(max_workers=args.max_queue) as pool:
        futs = {pool.submit(run, m, r): (m, r) for m, r in todo}
        for f in as_completed(futs):
            mode, row = futs[f]
            try:
                preds, out = f.result()
                done += 1
                best = f"{preds[0].score:.2f}" if preds else "-"
                print(f"[{done + failed}/{len(todo)}] {mode:<11} {row['product_id']:<8} {str(row['class_key']):<24} n={len(preds):<3} best={best}  {out.relative_to(ROOT)}")
            except (Sam3Error, OSError) as exc:
                failed += 1
                print(f"[{done + failed}/{len(todo)}] FAILED {mode} {row['image']}: {exc}", file=sys.stderr)
    print(f"done={done} failed={failed} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

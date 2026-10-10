"""Test whether SAM 3 recognises the generic prompts "fruit" and "vegetable".

Uses the same 10 images as ``sam3_textonly.py --limit 10`` (one crop per class) and runs
every prompt on each of them.  Overlays go to
overlay/sam3_generic_prompts/<prompt>/<class_key>/<image>.png and a summary table is printed.

    python scripts/sam3_generic_prompts.py
    python scripts/sam3_generic_prompts.py --classes tomatoes onions broccoli --limit 3
    python scripts/sam3_generic_prompts.py --prompts fruit vegetable "fresh produce"

At most ``--max-queue`` jobs (default 5) are ever submitted to the server at once.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SAM3"))
from sam3_client import Sam3Error, sam3  # noqa: E402
from sam3_textonly import CROPS, draw_overlay, pick  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompts", nargs="+", default=["fruit", "vegetable"])
    ap.add_argument("--limit", type=int, default=10, help="same selection as sam3_textonly.py --limit; 0 = the whole dataset")
    ap.add_argument("--classes", nargs="+", default=None, help="only these class_keys (e.g. vegetables); --limit counts images, taken round-robin over classes")
    ap.add_argument("--max-queue", type=int, default=5, help="max jobs in flight at the server")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--server", default=None)
    args = ap.parse_args()

    rows = [json.loads(line) for line in (CROPS / "dataset.jsonl").read_text().splitlines() if line.strip()]
    if args.classes:
        rows = [r for r in rows if r["class_key"] in args.classes]
    rows = pick(rows, args.limit or None)
    out_root = ROOT / "overlay" / "sam3_generic_prompts"

    def run(row: dict, prompt: str):
        src = CROPS / row["image"]
        out = out_root / prompt / row["class_key"] / (src.stem + ".png")
        preds = sam3(src, text_prompt=prompt, threshold=args.threshold, server=args.server)
        draw_overlay(src, preds, prompt, out)
        return preds, out

    jobs = [(r, p) for r in rows for p in args.prompts]
    print(f"{len(rows)} images x {len(args.prompts)} prompts = {len(jobs)} jobs, {args.max_queue} in flight at most")
    results: dict[tuple[str, str], list[list]] = {}
    t0, failed = time.time(), 0
    with ThreadPoolExecutor(max_workers=args.max_queue) as pool:
        futs = {pool.submit(run, r, p): (r, p) for r, p in jobs}
        for n, f in enumerate(as_completed(futs), 1):
            row, prompt = futs[f]
            try:
                preds, out = f.result()
                results.setdefault((row["class_key"], prompt), []).append(preds)
                best = f"{preds[0].score:.2f}" if preds else "-"
                print(f"[{n}/{len(jobs)}] {prompt:<10} {row['class_key']:<20} n={len(preds):<3} best={best}  {out.relative_to(ROOT)}")
            except (Sam3Error, OSError) as exc:
                failed += 1
                print(f"[{n}/{len(jobs)}] FAILED {prompt} {row['image']}: {exc}", file=sys.stderr)

    # summary per class and prompt: images with >=1 detection / images, most detections, best score
    print("\nclass                " + "".join(f"{p:<38}" for p in args.prompts))
    for k in dict.fromkeys(r["class_key"] for r in rows):
        cells = []
        for p in args.prompts:
            runs = results.get((k, p), [])
            hits = [r for r in runs if r]
            best = max((r[0].score for r in hits), default=0)
            cells.append(f"{len(hits)}/{len(runs)} img, max n={max(map(len, runs), default=0)}, best={best:.2f}")
        print(f"{k:<21}" + "".join(f"{c:<38}" for c in cells))
    print(f"\nfailed={failed} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

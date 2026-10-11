"""Run extra ("adversarial") text prompts on every crop of some products, to see whether they
catch the false positives of the product's own prompt.

The prompts are listed per product_id in output/crops/adversarial_prompts.json. An entry is a
text prompt, or an object that can also borrow the visual example (box on a crop) of another
product from examples_by_product.json, with or without text:

    {"15730": ["yellow potato", "packaged potatoes"],
     "18090": [{"prompt": "packed red potatoes", "example_from": "15753"}]}

    python scripts/sam3_adversarial.py                      # every product in the file
    python scripts/sam3_adversarial.py --product 15730      # only some of them

Overlays go to overlay/sam3_adversarial/<label>/<product_id>/<image>.png, where label is the
prompt, plus " [example <product_id>]" when an example is borrowed (finished ones are
skipped, ``--force`` redoes them); contact_sheets.py adds one column per listed prompt.
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
sys.path.insert(0, str(ROOT / "scripts"))
from sam3_client import Sam3Error, sam3  # noqa: E402
from sam3_textonly import CROPS, draw_overlay  # noqa: E402


def entry(item) -> tuple[str | None, str | None]:
    """(text prompt, example product_id) of one entry of the config."""
    if isinstance(item, str):
        return item, None
    return item.get("prompt"), (str(item["example_from"]) if item.get("example_from") else None)


def label(item) -> str:
    prompt, src = entry(item)
    return " ".join(x for x in (prompt, f"[example {src}]" if src else None) if x)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", nargs="+", default=None, help="only these product_ids (default: all in the file)")
    ap.add_argument("--config", type=Path, default=CROPS / "adversarial_prompts.json")
    ap.add_argument("--max-queue", type=int, default=5, help="max jobs in flight at the server")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--server", default=None)
    ap.add_argument("--force", action="store_true", help="redo overlays that already exist")
    args = ap.parse_args()

    config = {str(k): v for k, v in json.loads(args.config.read_text()).items()}
    if args.product:
        missing = [p for p in args.product if p not in config]
        if missing:
            ap.error(f"not in {args.config.name}: {missing}")
        config = {p: config[p] for p in args.product}
    rows = [json.loads(l) for l in (CROPS / "dataset.jsonl").read_text().splitlines() if l.strip()]
    examples = json.loads((CROPS / "examples_by_product.json").read_text())
    jobs = [(r, item) for r in rows for item in config.get(str(r["product_id"]), [])]

    def out_of(r: dict, item) -> Path:
        return ROOT / "overlay" / "sam3_adversarial" / label(item) / str(r["product_id"]) / (Path(r["image"]).stem + ".png")

    def run(r: dict, item):
        prompt, src = entry(item)
        kw = {}
        if src:
            ex = examples[src]
            kw = dict(example_image=CROPS / ex["image"], bounding_box_exemplar=[ex["box"]])
        preds = sam3(CROPS / r["image"], text_prompt=prompt, threshold=args.threshold, server=args.server, **kw)
        draw_overlay(CROPS / r["image"], preds, label(item), out_of(r, item))
        return preds

    todo = [(r, p) for r, p in jobs if args.force or not out_of(r, p).exists()]
    print(f"{len(config)} products, {len(jobs)} jobs, {len(todo)} to do")
    t0, done, failed = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=args.max_queue) as pool:
        futs = {pool.submit(run, r, p): (r, p) for r, p in todo}
        for f in as_completed(futs):
            r, item = futs[f]
            prompt = label(item)
            try:
                preds = f.result()
                done += 1
                best = f"{preds[0].score:.2f}" if preds else "-"
                print(f"[{done + failed}/{len(todo)}] {r['product_id']} {prompt!r:<22} n={len(preds):<3} best={best}  {out_of(r, item).relative_to(ROOT)}")
            except (Sam3Error, OSError) as exc:
                failed += 1
                print(f"[{done + failed}/{len(todo)}] FAILED {prompt!r} {r['image']}: {exc}", file=sys.stderr)
    print(f"done={done} failed={failed} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

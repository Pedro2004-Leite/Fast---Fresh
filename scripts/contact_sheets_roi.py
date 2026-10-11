"""Contact sheet per product_id with the occupied-area logic, one row per crop of the product.

Columns:
    1  text_visual            SAM 3 masks of the product's prompt + visual example
    2  fruit | vegetable | plastic package   union of the three generic prompts
    3  text_visual extended   each text_visual mask whose area lies >= --contain (95 %) inside
                              a generic mask is replaced by that generic mask (the group)
    4  ROI + column 3         ROI mask of the planogram area (output/crops/masks) in caramel,
                              its intersection with column 3 in green (occupied area)
    5  ROI + column 2         same with the union of column 2

SAM 3 masks are cached in output/sam3_masks/<product_id>/<image>.npz (``--force`` redoes them).

    python scripts/contact_sheets_roi.py --product 15730
    python scripts/contact_sheets_roi.py                    # every product with an example

Sheets go to output/contact_sheets_roi/<product_id>.png (``--out`` to change).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SAM3"))
sys.path.insert(0, str(ROOT / "scripts"))
from contact_sheets import BG, CARAMEL, CELL, FG, PAD, fit, font, planogram_names  # noqa: E402
from sam3_client import sam3  # noqa: E402
from sam3_textonly import CROPS, PALETTE  # noqa: E402

GENERIC = ("fruit", "vegetable", "plastic package")
GREEN = (60, 200, 90)


def segment(row: dict, ex: dict, cache: Path, args) -> dict[str, np.ndarray]:
    """{"text_visual": (n,H,W) bool, "fruit": ..., "vegetable": ..., "plastic package": ...}"""
    if cache.exists() and not args.force:
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    src = CROPS / row["image"]
    h, w = Image.open(src).size[::-1]

    def stack(preds) -> np.ndarray:
        return np.stack([p.full_mask() for p in preds]) if preds else np.zeros((0, h, w), bool)

    out = {"text_visual": stack(sam3(src, text_prompt=ex["prompt"], example_image=CROPS / ex["image"],
                                     bounding_box_exemplar=[ex["box"]], threshold=args.threshold,
                                     server=args.server))}
    for g in GENERIC:
        out[g] = stack(sam3(src, text_prompt=g, threshold=args.threshold, server=args.server))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **out)
    return out


def extend(text: np.ndarray, generic: np.ndarray, contain: float) -> tuple[np.ndarray, int]:
    """Union of the text masks, each swapped for the generic mask that contains >= ``contain``
    of it (the one with the most overlap). Returns (mask, number of masks swapped)."""
    out = np.zeros(text.shape[1:], bool)
    swapped = 0
    for t in text:
        area = t.sum()
        if area and len(generic):
            frac = (generic & t).sum(axis=(1, 2)) / area
            best = int(frac.argmax())
            if frac[best] >= contain:
                out |= generic[best]
                swapped += 1
                continue
        out |= t
    return out, swapped


def label_on(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = d.textbbox((4, 4), text)
    d.rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), fill=(0, 0, 0))
    d.text((4, 4), text, fill=(255, 255, 255))


def tint(base: np.ndarray, mask: np.ndarray, color, alpha=0.55) -> None:
    base[mask] = (1 - alpha) * base[mask] + alpha * np.array(color, np.float32)


def instances_overlay(img: Image.Image, masks: np.ndarray, label: str) -> Image.Image:
    base = np.asarray(img.convert("RGB")).astype(np.float32)
    for i, m in enumerate(masks):
        tint(base, m, PALETTE[i % len(PALETTE)], 0.5)
    out = Image.fromarray(base.astype(np.uint8))
    label_on(out, f"{label}: {len(masks)}")
    return out


def mask_overlay(img: Image.Image, mask: np.ndarray, label: str) -> Image.Image:
    base = np.asarray(img.convert("RGB")).astype(np.float32)
    tint(base, mask, PALETTE[3], 0.5)
    out = Image.fromarray(base.astype(np.uint8))
    label_on(out, label)
    return out


def roi_overlay(img: Image.Image, roi: np.ndarray, occ: np.ndarray) -> Image.Image:
    base = np.asarray(img.convert("RGB")).astype(np.float32)
    tint(base, roi, CARAMEL, 0.55)
    tint(base, roi & occ, GREEN, 0.75)
    out = Image.fromarray(base.astype(np.uint8))
    pct = 100 * (roi & occ).sum() / max(1, roi.sum())
    label_on(out, f"occupied {pct:.0f}% of ROI")
    return out


def sheet(pid: str, name: str, ex: dict, rows: list[dict], args) -> Path:
    f_big, f_mid, f_small = font(22), font(18), font(14)
    heads = ["text_visual", "fruit | vegetable | plastic package",
             f"text_visual extended (>= {args.contain:.0%} inside)",
             "ROI + column 3 (green = occupied)", "ROI + column 2 (green = occupied)"]

    def work(r: dict):
        cache = ROOT / "output" / "sam3_masks" / pid / (Path(r["image"]).stem + ".npz")
        m = segment(r, ex, cache, args)
        img = Image.open(CROPS / r["image"]).convert("RGB")
        roi = np.load(CROPS / r["mask"]).astype(bool)
        generic = np.concatenate([m[g] for g in GENERIC])
        union = generic.any(axis=0) if len(generic) else np.zeros(roi.shape, bool)
        ext, swapped = extend(m["text_visual"], generic, args.contain)
        cells = [instances_overlay(img, m["text_visual"], "text_visual"),
                 mask_overlay(img, union, f"union of {len(generic)} masks"),
                 mask_overlay(img, ext, f"{swapped}/{len(m['text_visual'])} swapped"),
                 roi_overlay(img, roi, ext), roi_overlay(img, roi, union)]
        return Path(r["image"]).stem, r["image"] == ex["image"], [fit(c) for c in cells]

    with ThreadPoolExecutor(max_workers=args.max_queue) as pool:
        body = list(pool.map(work, rows))

    width = PAD + len(heads) * (CELL + PAD)
    row_h = 20 + CELL + PAD
    canvas = Image.new("RGB", (width, PAD + 30 + 30 + len(body) * row_h + PAD), BG)
    d = ImageDraw.Draw(canvas)
    d.text((PAD, PAD), f"{pid}   {name}", font=f_big, fill=FG)
    d.text((PAD, PAD + 30), f'SAM prompt: "{ex["prompt"]}"   (class: {rows[0]["class_key"]})', font=f_mid, fill=FG)
    y = PAD + 60
    for i, h in enumerate(heads):
        d.text((PAD + i * (CELL + PAD), y), h, font=f_mid, fill=(255, 210, 120))
    y += 30
    for stem, is_ex, cells in body:
        d.text((PAD, y), stem + ("   [this is the visual example]" if is_ex else ""), font=f_small, fill=(160, 160, 160))
        for i, c in enumerate(cells):
            canvas.paste(c, (PAD + i * (CELL + PAD), y + 20))
        y += row_h
    out = args.out / f"{pid}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", nargs="+", default=None, help="product_ids (default: all with an example)")
    ap.add_argument("--contain", type=float, default=0.95, help="fraction of a text mask inside a generic mask")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--max-queue", type=int, default=5, help="max jobs in flight at the server")
    ap.add_argument("--server", default=None)
    ap.add_argument("--force", action="store_true", help="redo cached SAM 3 masks")
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "contact_sheets_roi")
    args = ap.parse_args()

    examples = json.loads((CROPS / "examples_by_product.json").read_text())
    names = planogram_names()
    dataset = [json.loads(l) for l in (CROPS / "dataset.jsonl").read_text().splitlines() if l.strip()]
    for pid in args.product or sorted(examples):
        rows = sorted((r for r in dataset if str(r["product_id"]) == pid), key=lambda r: r["image"])
        out = sheet(pid, names.get(pid, "(not in planogram.json)"), examples[pid], rows, args)
        print(f"{pid}: {len(rows)} images -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

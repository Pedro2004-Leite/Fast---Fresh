"""Shelf analysis: planogram + camera images -> compliance and stock level per planogram area.

For every area of every image:
    1. crop a square window around the area and build the ROI mask (polygon of the area)
    2. SAM 3 on the crop -> "specific" product (text prompt + visual example of the product,
       each mask swapped for the generic mask that contains it) and "general" product (union of
       fruit / vegetable / plastic package), the same two areas as in output/contact_sheets_roi
    3. spec_frac = |ROI & specific| / |ROI|,  gen_frac = |ROI & general| / |ROI|
    4. decision:
        spec_frac >= min_present and spec_frac >= min_ratio * gen_frac
                                   -> compliant; level from spec_frac
        else gen_frac >= min_general -> NOT compliant (other product); level from gen_frac
        else                        -> compliant, empty
       level: empty if frac < empty_max, half if frac < full_min, else full.
       Overestimating stock costs more than underestimating it, so keep full_min on the high side.

Thresholds: ``--thresholds file.json`` holds {"default": {...}, "products": {"<product_id>": {...}}};
any of min_present, min_ratio, min_general, empty_max, full_min can be set per product.
CLI flags change the defaults.

    python scripts/analyse_shelf.py --cameras 6215 6383 --per-camera 1 --debug
    python scripts/analyse_shelf.py --images dataset/train --out output/analysis

Outputs in --out: predictions.json (annotations.json format), details.json (fractions and
reason per area), debug/<camera>__<image>.png (with --debug), cache/ (SAM 3 masks).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SAM3"))
sys.path.insert(0, str(ROOT / "scripts"))
from contact_sheets import BG, CELL, FG, PAD, fit, font  # noqa: E402
from contact_sheets_roi import GENERIC, extend, roi_overlay  # noqa: E402
from crop_planogram import IMAGE_EXTENSIONS, _bbox_by_excess, _quad, _square_window  # noqa: E402
from sam3_client import sam3  # noqa: E402

CROPS = ROOT / "output" / "crops"
STOCK_VALUE = {"empty": 0.0, "half": 0.5, "full": 1.0}


@dataclass
class Thresholds:
    min_present: float = 0.05   # specific area below this fraction of the ROI = not there
    min_ratio: float = 0.20     # specific must be at least this share of the general area
    min_general: float = 0.05   # general area below this fraction of the ROI = nothing there
    empty_max: float = 0.15     # fraction below this -> empty
    full_min: float = 0.55      # fraction from this -> full (between: half)


def load_thresholds(args) -> tuple[Thresholds, dict[str, Thresholds]]:
    base = Thresholds(**{f.name: getattr(args, f.name) for f in fields(Thresholds)})
    per_product: dict[str, Thresholds] = {}
    if args.thresholds:
        cfg = json.loads(args.thresholds.read_text())
        base = Thresholds(**{**asdict(base), **cfg.get("default", {})})
        for pid, over in cfg.get("products", {}).items():
            per_product[str(pid)] = Thresholds(**{**asdict(base), **over})
    return base, per_product


def level(frac: float, t: Thresholds) -> str:
    return "empty" if frac < t.empty_max else "half" if frac < t.full_min else "full"


def decide(spec: float, gen: float, t: Thresholds) -> dict:
    if spec >= t.min_present and spec >= t.min_ratio * gen:
        return {"planogram_compliant": True, "stock_level": level(spec, t), "reason": "specific product present"}
    if gen >= t.min_general:
        why = "specific product too small" if spec >= t.min_present else "no specific product"
        return {"planogram_compliant": False, "stock_level": level(gen, t), "reason": f"{why}, general product present"}
    return {"planogram_compliant": True, "stock_level": "empty", "reason": "nothing detected"}


def load_examples() -> dict[str, dict]:
    """product_id -> {prompt, image, box}; examples_by_product.json first, examples.json by class."""
    by_product = json.loads((CROPS / "examples_by_product.json").read_text())
    by_class = json.loads((CROPS / "examples.json").read_text())
    classes = json.loads((ROOT / "dataset" / "classes.json").read_text())
    out = dict(by_product)
    for class_key, pids in classes.items():
        ex = by_class.get(class_key)
        for pid in pids:
            if str(pid) not in out and ex:
                out[str(pid)] = {**ex, "prompt": ex.get("prompt", class_key)}
    return out


def make_jobs(planogram: dict, images_dir: Path, cameras, per_camera, names) -> list[dict]:
    """One job per (image, camera), with its areas."""
    cams = next(iter(planogram.values()))["cameras"]
    jobs = []
    for cam, data in cams.items():
        if cameras and cam not in cameras:
            continue
        folder = images_dir / cam
        if not folder.is_dir() and images_dir.name == cam:
            folder = images_dir
        files = sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXTENSIONS) if folder.is_dir() else []
        if names:
            files = [p for p in files if p.name in names]
        if per_camera:
            files = files[:per_camera]
        jobs += [{"camera": cam, "path": p, "areas": data["products"]} for p in files]
    return jobs


def stack(preds, hw) -> np.ndarray:
    return np.stack([p.full_mask() for p in preds]) if preds else np.zeros((0, *hw), bool)


def segment(crop: Image.Image, ex: dict, cache: Path, args) -> dict[str, np.ndarray]:
    if cache.exists() and not args.force:
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    hw = crop.size[::-1]
    out = {"text_visual": stack(sam3(crop, text_prompt=ex["prompt"], example_image=CROPS / ex["image"],
                                     bounding_box_exemplar=[ex["box"]], threshold=args.threshold,
                                     server=args.server), hw)}
    for g in GENERIC:
        out[g] = stack(sam3(crop, text_prompt=g, threshold=args.threshold, server=args.server), hw)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **out)
    return out


def analyse_area(img: Image.Image, area: dict, side: int, ex: dict, t: Thresholds, cache_dir: Path, stem: str, args):
    quad = _quad(area["image_coordinates"])
    w, h = img.size
    x0, y0, x1, y1 = _bbox_by_excess(quad)
    if min(w, x1) - max(0, x0) <= 0 or min(h, y1) - max(0, y0) <= 0:
        return None
    sq = _square_window([x0, y0, x1, y1], side, w, h)
    crop = img.crop(tuple(sq))
    roi_img = Image.new("L", (side, side), 0)
    ImageDraw.Draw(roi_img).polygon([(x - sq[0], y - sq[1]) for x, y in quad], fill=255)
    roi = np.asarray(roi_img) > 0

    m = segment(crop, ex, cache_dir / f"{stem}__{area['area_id']}.npz", args)
    generic = np.concatenate([m[g] for g in GENERIC])
    general = generic.any(axis=0) if len(generic) else np.zeros(roi.shape, bool)
    specific, _ = extend(m["text_visual"], generic, args.contain)
    n = max(1, int(roi.sum()))
    spec, gen = float((roi & specific).sum() / n), float((roi & general).sum() / n)
    return {"crop": crop, "roi": roi, "specific": specific, "general": general,
            "spec_frac": spec, "gen_frac": gen, **decide(spec, gen, t)}


def debug_sheet(rows: list[tuple[dict, dict]], title: str, out: Path) -> None:
    f_big, f_small = font(20), font(15)
    heads = ["crop", "ROI + specific (green)", "ROI + general (green)"]
    row_h = CELL + 52
    canvas = Image.new("RGB", (PAD + 3 * (CELL + PAD), PAD + 30 + len(rows) * row_h), BG)
    d = ImageDraw.Draw(canvas)
    d.text((PAD, PAD), title, font=f_big, fill=FG)
    y = PAD + 30
    for area, r in rows:
        txt = (f"{area['area_id']}  {area['product_id']}  {area['product_name']}\n"
               f"specific {r['spec_frac']:.0%}  general {r['gen_frac']:.0%}  -> "
               f"{'compliant' if r['planogram_compliant'] else 'NOT compliant'}, {r['stock_level']}  ({r['reason']})")
        d.multiline_text((PAD, y), txt, font=f_small, fill=FG)
        cells = [r["crop"].convert("RGB"), roi_overlay(r["crop"], r["roi"], r["specific"]),
                 roi_overlay(r["crop"], r["roi"], r["general"])]
        for i, c in enumerate(cells):
            canvas.paste(fit(c), (PAD + i * (CELL + PAD), y + 46))
        y += row_h
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--planogram", type=Path, default=ROOT / "dataset" / "planogram.json")
    ap.add_argument("--images", type=Path, default=ROOT / "dataset" / "train", help="folder with one subfolder per camera")
    ap.add_argument("--cameras", nargs="+", default=None, help="camera ids (default: all)")
    ap.add_argument("--files", nargs="+", default=None, help="only these image file names")
    ap.add_argument("--per-camera", type=int, default=None, help="only the first N images of each camera")
    ap.add_argument("--areas", nargs="+", default=None, help="only these area_ids")
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "analysis")
    ap.add_argument("--debug", action="store_true", help="write one overlay sheet per image")
    ap.add_argument("--thresholds", type=Path, default=None, help="JSON with per-product thresholds")
    for f in fields(Thresholds):
        ap.add_argument(f"--{f.name.replace('_', '-')}", dest=f.name, type=float, default=f.default)
    ap.add_argument("--contain", type=float, default=0.95, help="fraction of a text mask inside a generic mask")
    ap.add_argument("--threshold", type=float, default=0.30, help="SAM 3 score threshold")
    ap.add_argument("--max-queue", type=int, default=5, help="areas in flight at the server")
    ap.add_argument("--server", default=None)
    ap.add_argument("--force", action="store_true", help="redo cached SAM 3 masks")
    args = ap.parse_args()

    planogram = json.loads(args.planogram.read_text())
    cams = next(iter(planogram.values()))["cameras"]
    # same global side as crop_planogram.py, so crops look like the visual examples
    side = 0
    for data in cams.values():
        for a in data["products"]:
            bx = _bbox_by_excess(_quad(a["image_coordinates"]))
            side = max(side, bx[2] - bx[0], bx[3] - bx[1])

    default_t, per_product = load_thresholds(args)
    examples = load_examples()
    # SAM 3 mask cache depends on the SAM 3 parameters only, never on the decision thresholds
    tag = hashlib.md5(f"{args.threshold}".encode()).hexdigest()[:6]
    cache_dir = args.out / "cache" / tag

    jobs = make_jobs(planogram, args.images, args.cameras, args.per_camera, set(args.files or []))
    if not jobs:
        sys.exit(f"no images found for the planogram cameras in {args.images}")
    predictions: dict = {}
    details: dict = {}
    for job in jobs:
        cam, path = job["camera"], job["path"]
        areas = [a for a in job["areas"] if not args.areas or a["area_id"] in args.areas]
        with Image.open(path) as im:
            img = im.convert("RGB")

        def work(a: dict):
            pid = str(a["product_id"])
            if pid not in examples:
                return a, None
            return a, analyse_area(img, a, side, examples[pid], per_product.get(pid, default_t),
                                   cache_dir, f"{cam}__{path.stem}", args)

        with ThreadPoolExecutor(max_workers=args.max_queue) as pool:
            results = list(pool.map(work, areas))

        sheet_rows = []
        for a, r in results:
            if r is None:  # no example or area outside the image: still emit the area (a missing one costs more)
                r = {"spec_frac": 0.0, "gen_frac": 0.0, "crop": None, **decide(0.0, 0.0, default_t),
                     "reason": "not analysed (no example or outside the image)"}
            else:
                sheet_rows.append((a, r))
            predictions.setdefault(cam, {}).setdefault(path.name, {})[a["area_id"]] = {
                "planogram_compliant": r["planogram_compliant"], "stock_level": r["stock_level"],
                "stock_value": STOCK_VALUE[r["stock_level"]]}
            details.setdefault(cam, {}).setdefault(path.name, {})[a["area_id"]] = {
                "product_id": str(a["product_id"]), "specific_fraction": round(r["spec_frac"], 4),
                "general_fraction": round(r["gen_frac"], 4), "reason": r["reason"]}
            print(f"{a['area_id']:>8} {path.name}  spec {r['spec_frac']:5.1%}  gen {r['gen_frac']:5.1%}  "
                  f"{'ok ' if r['planogram_compliant'] else 'WRONG'} {r['stock_level']:5}  {r['reason']}")
        if args.debug and sheet_rows:
            debug_sheet(sheet_rows, f"{cam}  {path.name}", args.out / "debug" / f"{cam}__{path.stem}.png")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "predictions.json").write_text(json.dumps(predictions, indent=1))
    (args.out / "details.json").write_text(json.dumps(details, indent=1))
    print(f"wrote {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}/predictions.json")


if __name__ == "__main__":
    main()

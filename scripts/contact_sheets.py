"""One contact sheet per product_id to check the SAM 3 results by eye.

Top: product description (planogram.json), SAM 3 prompt, and the visual example twice
(its bounding box; its mask in caramel). Below: one row per crop of the product with four
columns: overlay/sam3_visual/text_visual, overlay/sam3_generic_prompts/fruit, .../vegetable,
.../plastic package.

    python scripts/contact_sheets.py --product 32748     # one sheet
    python scripts/contact_sheets.py                     # every product with an example

Sheets go to output/contact_sheets/<product_id>.png (``--out`` to change).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CROPS = ROOT / "output" / "crops"
OVERLAY = ROOT / "overlay"
CARAMEL = (196, 122, 40)
CELL = 400          # every picture is fitted in a CELL x CELL square
PAD, BG, FG = 12, (30, 30, 30), (230, 230, 230)
COLUMNS = [("text_visual", lambda r, pid: OVERLAY / "sam3_visual" / "text_visual" / pid),
           ("fruit", lambda r, pid: OVERLAY / "sam3_generic_prompts" / "fruit" / r["class_key"]),
           ("vegetable", lambda r, pid: OVERLAY / "sam3_generic_prompts" / "vegetable" / r["class_key"]),
           ("plastic package", lambda r, pid: OVERLAY / "sam3_generic_prompts" / "plastic package" / r["class_key"])]


def font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def fit(img: Image.Image) -> Image.Image:
    s = CELL / max(img.size)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def with_box(img: Image.Image, box) -> Image.Image:
    img = img.convert("RGB")
    ImageDraw.Draw(img).rectangle(box, outline=(255, 255, 0), width=2)
    return img


def with_mask(img: Image.Image, mask_path: Path) -> Image.Image:
    base = np.asarray(img.convert("RGB")).astype(np.float32)
    m = np.load(mask_path).astype(bool)
    base[m] = 0.45 * base[m] + 0.55 * np.array(CARAMEL, dtype=np.float32)
    return Image.fromarray(base.astype(np.uint8))


def planogram_names() -> dict[str, str]:
    names: dict[str, set[str]] = {}
    plano = json.loads((ROOT / "dataset" / "planogram.json").read_text())
    for top in plano.values():
        for cam in top["cameras"].values():
            for p in cam["products"]:
                names.setdefault(str(p["product_id"]), set()).add(p["product_name"])
    return {pid: " | ".join(sorted(v)) for pid, v in names.items()}


def sheet(pid: str, name: str, ex: dict, rows: list[dict], out: Path) -> None:
    f_big, f_mid, f_small = font(22), font(18), font(14)
    ex_img = Image.open(CROPS / ex["image"])
    ex_mask = CROPS / (ex["image"].replace("images/", "masks/").rsplit(".", 1)[0] + ".npy")
    top = [("example + box", fit(with_box(ex_img, ex["box"]))), ("example + mask", fit(with_mask(ex_img, ex_mask)))]

    ncol = len(COLUMNS)
    width = PAD + ncol * (CELL + PAD)
    # rows: (filename, [image or None per column])
    body = []
    for r in rows:
        stem = Path(r["image"]).stem + ".png"
        cells = []
        for _, where in COLUMNS:
            p = where(r, pid) / stem
            cells.append(fit(Image.open(p).convert("RGB")) if p.exists() else None)
        body.append((stem, r["image"] == ex["image"], cells))

    head_h = 2 * 30 + PAD + 22 + max(im.height for _, im in top) + PAD
    heights = [20 + max([c.height for c in cells if c] + [40]) + PAD for _, _, cells in body]
    canvas = Image.new("RGB", (width, head_h + 30 + sum(heights) + PAD), BG)
    d = ImageDraw.Draw(canvas)
    d.text((PAD, PAD), f"{pid}   {name}", font=f_big, fill=FG)
    d.text((PAD, PAD + 30), f'SAM prompt: "{ex["prompt"]}"   (class: {rows[0]["class_key"]})', font=f_mid, fill=FG)
    y = 2 * 30 + PAD
    for i, (label, im) in enumerate(top):
        x = PAD + i * (CELL + PAD)
        d.text((x, y), label, font=f_small, fill=(160, 160, 160))
        canvas.paste(im, (x, y + 22))
    y = head_h
    for i, (label, _) in enumerate(COLUMNS):
        d.text((PAD + i * (CELL + PAD), y), label, font=f_mid, fill=(255, 210, 120))
    y += 30
    for (stem, is_example, cells), h in zip(body, heights):
        d.text((PAD, y), stem + ("   [this is the visual example]" if is_example else ""), font=f_small, fill=(160, 160, 160))
        for i, c in enumerate(cells):
            x = PAD + i * (CELL + PAD)
            if c is not None:
                canvas.paste(c, (x, y + 20))
            else:
                d.text((x, y + 24), "(no overlay)", font=f_small, fill=(120, 120, 120))
        y += h
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", nargs="+", default=None, help="product_ids (default: all with an example)")
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "contact_sheets")
    args = ap.parse_args()

    examples = json.loads((CROPS / "examples_by_product.json").read_text())
    names = planogram_names()
    dataset = [json.loads(l) for l in (CROPS / "dataset.jsonl").read_text().splitlines() if l.strip()]
    for pid in args.product or sorted(examples):
        ex = examples[pid]
        rows = sorted((r for r in dataset if str(r["product_id"]) == pid), key=lambda r: r["image"])
        out = args.out / f"{pid}.png"
        sheet(pid, names.get(pid, "(not in planogram.json)"), ex, rows, out)
        print(f"{pid}: {len(rows)} images -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

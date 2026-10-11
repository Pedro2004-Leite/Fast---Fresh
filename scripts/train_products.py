"""YOLO11s-seg on product_ids, one class per product_id, SAM 3 text_visual masks as GT.

Masks come from the cache of scripts/contact_sheets_roi.py (output/sam3_masks/<pid>/<image>.npz,
key "text_visual"). Each crop is one camera/area of one product, so the split is temporal:
the last ``--val`` frames of each area are validation (the frames are near duplicates of
each other, so the val numbers are optimistic).

    python scripts/train_products.py build                       # all products -> output/products-all/
    python scripts/train_products.py train --epochs 100
    python scripts/train_products.py overlay                     # val + a few train crops per product
    python scripts/train_products.py build --products 11919 13702 32170 --tag yolo_products   # the 3-apple set

Everything is keyed by ``--tag`` (default products-all): dataset in output/<tag>/, run in
runs/<tag>/, overlays in overlay/<tag>/{train,val}/<product_id>/ (left GT, right prediction).
"""
from __future__ import annotations

import argparse
import colorsys
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CROPS = ROOT / "output" / "crops"
MASKS = ROOT / "output" / "sam3_masks"

MIN_AREA = 40          # px, drops specks
MAX_MEDIAN_X = 5.0     # drops pile-sized blobs: > 5x the median mask of the product
DEDUP_IOU = 0.8


def clean(masks: np.ndarray, med: float) -> np.ndarray:
    """Drop specks, pile-sized blobs and near-duplicates (the larger score order is unknown, keep first)."""
    keep: list[np.ndarray] = []
    for m in masks:
        a = int(m.sum())
        if a < MIN_AREA or a > MAX_MEDIAN_X * med:
            continue
        if any((m & k).sum() / max(1, (m | k).sum()) > DEDUP_IOU for k in keep):
            continue
        keep.append(m)
    return np.stack(keep) if keep else np.zeros((0, *masks.shape[1:]), bool)


def polygon(m: np.ndarray) -> np.ndarray | None:
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cs = [c for c in cs if len(c) >= 3]
    if not cs:
        return None
    return max(cs, key=cv2.contourArea)[:, 0, :].astype(np.float32)


def ds_dir(a) -> Path:
    return ROOT / "output" / a.tag


def color(i: int, n: int) -> tuple[int, int, int]:
    """Class colour: golden-ratio hue steps so neighbouring class ids differ."""
    r, g, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.85, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def image_owner() -> dict[str, str]:
    """crop stem -> product_id (dataset.jsonl)."""
    rows = (json.loads(l) for l in (CROPS / "dataset.jsonl").read_text().splitlines() if l.strip())
    return {Path(r["image"]).stem: str(r["product_id"]) for r in rows}


def build(a) -> None:
    DS = ds_dir(a)
    if DS.exists():
        shutil.rmtree(DS)
    pids = a.products or sorted(p.name for p in MASKS.iterdir() if p.is_dir())
    # (pid, area, stem, split, raw masks, polygons)
    items, cls_of = [], {}
    for pid in pids:
        files = sorted(MASKS.glob(f"{pid}/*.npz"), key=lambda p: p.stem.rsplit("__", 1)[1])
        raw = {f: np.load(f)["text_visual"] for f in files}
        areas = {}
        for f in files:
            areas.setdefault(f.stem.split("__")[0], []).append(f)
        sizes = [int(m.sum()) for ms in raw.values() for m in ms]
        if not sizes:
            continue
        med = float(np.median(sizes))
        for area, fs in areas.items():
            for k, f in enumerate(fs):
                split = "val" if k >= len(fs) - a.val else "train"
                masks = clean(raw[f], med)
                polys = [p for p in map(polygon, masks) if p is not None]
                shape = masks.shape[1:] if len(masks) else raw[f].shape[1:]
                items.append((pid, area, f.stem, split, len(raw[f]), polys, shape))
    # classes = products that kept at least one mask, in id order
    kept = sorted({it[0] for it in items if it[5]}, key=lambda p: (len(p), p))
    cls_of = {p: i for i, p in enumerate(kept)}
    for pid, area, stem, split, n_raw, polys, (h, w) in items:
        if pid not in cls_of:
            continue
        src = CROPS / "images" / (stem + ".png")
        (DS / "images" / split).mkdir(parents=True, exist_ok=True)
        (DS / "labels" / split).mkdir(parents=True, exist_ok=True)
        shutil.copy(src, DS / "images" / split / src.name)
        lines = [f"{cls_of[pid]} " + " ".join(f"{v:.5f}" for v in (p / [w, h]).ravel()) for p in polys]
        (DS / "labels" / split / (stem + ".txt")).write_text("\n".join(lines))
    (DS / "data.yaml").write_text(
        f"path: {DS}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: '{p}'\n" for p, i in cls_of.items()))
    for s in ("train", "val"):
        r = [it for it in items if it[3] == s and it[0] in cls_of]
        print(f"{s:<5} images={len(r):<5} masks raw={sum(x[4] for x in r):<6} kept={sum(len(x[5]) for x in r)}")
    dropped = sorted(set(pids) - set(cls_of))
    print(f"{len(cls_of)} classes" + (f", dropped without masks: {dropped}" if dropped else ""))


def train(a) -> None:
    from ultralytics import YOLO
    YOLO(a.model).train(
        data=str(ds_dir(a) / "data.yaml"), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device,
        project=str(ROOT / "runs"), name=a.tag, patience=a.patience, exist_ok=True, seed=0,
        # the camera is fixed and the crops are tiny: mild geometry, no vertical flip, mosaic helps with few images
        flipud=0.0, degrees=0.0, close_mosaic=15,
    )


def read_gt(label: Path, w: int, h: int) -> list[tuple[int, np.ndarray]]:
    out = []
    if label.exists():
        for ln in label.read_text().splitlines():
            t = ln.split()
            out.append((int(t[0]), (np.array(t[1:], np.float32).reshape(-1, 2) * [w, h]).astype(np.int32)))
    return out


def tint(img: Image.Image, polys: list[tuple[int, np.ndarray]], title: str, n_cls: int) -> Image.Image:
    base = np.asarray(img.convert("RGB")).copy()
    over = base.copy()
    for c, p in polys:
        cv2.fillPoly(over, [p], color(c, n_cls))
    base = cv2.addWeighted(over, 0.5, base, 0.5, 0)
    for c, p in polys:
        cv2.polylines(base, [p], True, color(c, n_cls), 1)
    out = Image.fromarray(base)
    d = ImageDraw.Draw(out)
    d.rectangle((0, 0, out.width, 14), fill=(0, 0, 0))
    d.text((3, 1), title, fill=(255, 255, 255))
    return out


def overlay(a) -> None:
    from ultralytics import YOLO
    DS = ds_dir(a)
    model = YOLO(a.weights or str(ROOT / "runs" / a.tag / "weights" / "best.pt"))
    names = model.names
    n_cls = len(names)
    owner = image_owner()
    out_root = ROOT / "overlay" / a.tag
    if out_root.exists():
        shutil.rmtree(out_root)
    for split in ("train", "val"):
        seen: dict[str, int] = {}
        for img_path in sorted((DS / "images" / split).glob("*.png")):
            pid = owner[img_path.stem]
            if split == "train":
                if seen.get(pid, 0) >= a.train_per_product:
                    continue
                seen[pid] = seen.get(pid, 0) + 1
            img = Image.open(img_path).convert("RGB")
            w, h = img.size
            gt = read_gt(DS / "labels" / split / (img_path.stem + ".txt"), w, h)
            r = model.predict(img_path, imgsz=a.imgsz, conf=a.conf, device=a.device, verbose=False)[0]
            pred = []
            if r.masks is not None:
                pred = [(int(c), p.astype(np.int32)) for c, p in zip(r.boxes.cls.cpu().numpy(), r.masks.xy) if len(p) >= 3]
            wrong = sum(names[c] != pid for c, _ in pred)
            panel = Image.new("RGB", (2 * w, h))
            panel.paste(tint(img, gt, f"GT {pid}: {len(gt)}", n_cls), (0, 0))
            panel.paste(tint(img, pred, f"pred: {len(pred)} (wrong class {wrong})", n_cls), (w, 0))
            dst = out_root / split / pid / (img_path.stem + ".png")
            dst.parent.mkdir(parents=True, exist_ok=True)
            panel.save(dst)
    print(f"overlays in {out_root.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="products-all", help="names the dataset dir, run and overlay dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--products", nargs="+", default=None, help="product_ids (default: every cached product)")
    b.add_argument("--val", type=int, default=3, help="last N frames of each area go to val")
    t = sub.add_parser("train")
    t.add_argument("--model", default="weights/yolo11s-seg.pt")
    t.add_argument("--epochs", type=int, default=100)
    t.add_argument("--imgsz", type=int, default=320)
    t.add_argument("--batch", type=int, default=32)
    t.add_argument("--patience", type=int, default=30)
    t.add_argument("--device", default="0")
    o = sub.add_parser("overlay")
    o.add_argument("--weights")
    o.add_argument("--imgsz", type=int, default=320)
    o.add_argument("--conf", type=float, default=0.15)
    o.add_argument("--device", default="0")
    o.add_argument("--train-per-product", type=int, default=2, help="train crops per product (val: all)")
    a = ap.parse_args()
    {"build": build, "train": train, "overlay": overlay}[a.cmd](a)


if __name__ == "__main__":
    main()

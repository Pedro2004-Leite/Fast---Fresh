"""Inference cost per product_id from the crop index and the measured latency.

Cost is derived, not metered: crops x jobs per crop x seconds per job x GPU price.
analyse_shelf.py makes 4 SAM 3 jobs per area (text + visual example, then fruit, vegetable,
plastic package); the YOLO11s-seg model replaces them with one forward pass.

    python scripts/inference_cost.py --eur-per-hour 1.0
    python scripts/inference_cost.py --eur-per-hour 1.0 --frames-per-day 20 --csv output/cost.csv

Without --eur-per-hour only GPU seconds are printed.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAM3_JOBS_PER_AREA = 4


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, default=ROOT / "output" / "crops" / "dataset.jsonl")
    ap.add_argument("--sam3-s", type=float, default=0.126, help="seconds per SAM 3 job (scripts/sam3_profile.py, best concurrency)")
    ap.add_argument("--yolo-ms", type=float, default=2.9, help="YOLO11s-seg ms per crop (1.1 inference + 0.3 + 1.5)")
    ap.add_argument("--eur-per-hour", type=float, default=None, help="GPU price; not known, no default")
    ap.add_argument("--frames-per-day", type=int, default=None, help="scale to this many frames per camera per day")
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args()

    rows = [json.loads(l) for l in a.index.read_text().splitlines() if l.strip()]
    crops = Counter(r["product_id"] for r in rows)
    n_images = len({Path(r["image"]).stem.split("__")[-1] for r in rows})
    out = []
    for pid, n in sorted(crops.items(), key=lambda kv: -kv[1]):
        sam_s = n * SAM3_JOBS_PER_AREA * a.sam3_s
        yolo_s = n * a.yolo_ms / 1000
        out.append({"product_id": pid, "crops": n, "sam3_gpu_s": round(sam_s, 1), "yolo_gpu_s": round(yolo_s, 2),
                    "sam3_s_per_crop": round(SAM3_JOBS_PER_AREA * a.sam3_s, 2)})
        if a.eur_per_hour is not None:
            out[-1]["sam3_eur"] = sam_s / 3600 * a.eur_per_hour
            out[-1]["yolo_eur"] = yolo_s / 3600 * a.eur_per_hour
    tot_sam, tot_yolo = sum(r["sam3_gpu_s"] for r in out), sum(r["yolo_gpu_s"] for r in out)
    print(f"{len(rows)} crops, {len(out)} products, {n_images} distinct frames")
    print(f"SAM 3: {SAM3_JOBS_PER_AREA} jobs x {a.sam3_s} s = {SAM3_JOBS_PER_AREA * a.sam3_s:.2f} s per crop, {tot_sam:.0f} GPU s in total")
    print(f"YOLO : {a.yolo_ms} ms per crop, {tot_yolo:.1f} GPU s in total")
    if a.eur_per_hour is not None:
        print(f"at {a.eur_per_hour} EUR/h: SAM 3 {tot_sam / 3600 * a.eur_per_hour:.4f} EUR, "
              f"YOLO {tot_yolo / 3600 * a.eur_per_hour:.6f} EUR for the whole set; "
              f"{SAM3_JOBS_PER_AREA * a.sam3_s / 3600 * a.eur_per_hour * 1000:.4f} EUR per 1000 crops (SAM 3)")
    for r in out[:10]:
        print(r)
    if a.csv:
        a.csv.parent.mkdir(parents=True, exist_ok=True)
        with a.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0]))
            w.writeheader()
            w.writerows(out)
        print("wrote", a.csv)


if __name__ == "__main__":
    main()

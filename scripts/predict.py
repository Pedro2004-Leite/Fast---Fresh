"""Run YOLO11 on images (smoke test, or pre-label with --save-txt to bootstrap annotation).

    python scripts/predict.py detect  dataset/train/6215
    python scripts/predict.py segment dataset/train/6215 --save-txt --conf 0.25
"""
import argparse
from pathlib import Path
from ultralytics import YOLO

DEFAULTS = {"detect": "weights/yolo11m.pt", "segment": "weights/yolo11m-seg.pt"}

ap = argparse.ArgumentParser()
ap.add_argument("task", choices=DEFAULTS)
ap.add_argument("source")
ap.add_argument("--model", help="weights; default is the COCO-pretrained one, use runs/<name>/weights/best.pt after fine-tuning")
ap.add_argument("--conf", type=float, default=0.25)
ap.add_argument("--imgsz", type=int, default=1280)
ap.add_argument("--device", default="0")
ap.add_argument("--save-txt", action="store_true", help="write YOLO-format label files")
a = ap.parse_args()

YOLO(a.model or DEFAULTS[a.task]).predict(
    a.source, conf=a.conf, imgsz=a.imgsz, device=a.device,
    save=True, save_txt=a.save_txt, project=str(Path(__file__).resolve().parent.parent / "runs"), name=f"predict-{a.task}",
)

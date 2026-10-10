"""Fine-tune YOLO11 for detection (bounding boxes) or instance segmentation.

    python scripts/train.py detect  --epochs 100
    python scripts/train.py segment --epochs 100 --device 0
"""
import argparse
from pathlib import Path
from ultralytics import YOLO

TASKS = {
    "detect": ("weights/yolo11m.pt", "configs/detect.yaml"),
    "segment": ("weights/yolo11m-seg.pt", "configs/segment.yaml"),
}

ap = argparse.ArgumentParser()
ap.add_argument("task", choices=TASKS)
ap.add_argument("--model", help="override starting weights")
ap.add_argument("--data", help="override dataset yaml")
ap.add_argument("--epochs", type=int, default=100)
ap.add_argument("--imgsz", type=int, default=1280)  # source images are 1280x720, products are small
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--device", default="0")
ap.add_argument("--name")
a = ap.parse_args()

weights, data = TASKS[a.task]
YOLO(a.model or weights).train(
    data=a.data or data,
    epochs=a.epochs,
    imgsz=a.imgsz,
    batch=a.batch,
    device=a.device,
    project=str(Path(__file__).resolve().parent.parent / "runs"),
    name=a.name or a.task,
    patience=30,
)

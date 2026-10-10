# Fast---Fresh

YOLO11 setup for shelf monitoring (fruits & vegetables): bounding-box detection and instance segmentation, ready for fine-tuning.

## Setup
    pip install -r requirements.txt
Pretrained COCO weights (`yolo11m.pt`, `yolo11m-seg.pt`) live in `weights/` (git-ignored; re-downloaded automatically by Ultralytics).

## Layout
- `configs/detect.yaml`, `configs/segment.yaml` - dataset configs (edit `names` to the real classes)
- `scripts/train.py` - fine-tune (`detect` or `segment`)
- `scripts/predict.py` - inference / pre-labelling (`--save-txt`)
- `data/{detect,segment}/images|labels/{train,val}` - labelled data, YOLO format (git-ignored)

- `SAM3/` - SAM 3 web service (resident model per GPU, queue) and its `sam3()` client; see `SAM3/README.md`

## Usage
    python scripts/predict.py detect dataset/train/6215
    python scripts/train.py detect  --epochs 100
    python scripts/train.py segment --epochs 100

"""Build a (square crop, quad mask, class) dataset from shelf images and a planogram (deterministic, no ML)."""

import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

log = logging.getLogger("crop_planogram")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CORNER_KEYS = ("top_left", "top_right", "bottom_right", "bottom_left")
PACKAGED_PREFIX = "packaged "
PACKAGED_SUFFIX_PT = " (embalada)"

# Portuguese display names for the base (loose) concepts; "packaged X" derives from X.
PT_NAMES = {
    "apples": "Maçã", "apricots": "Alperce", "avocados": "Abacate", "bananas": "Banana",
    "broccoli": "Brócolos", "cabbages": "Couve branca", "cauliflower": "Couve-flor",
    "chayotes": "Chuchu", "cherries": "Cereja", "cherry tomatoes": "Tomate cherry",
    "collard greens": "Couve portuguesa", "cucumbers": "Pepino", "dragon fruits": "Pitaya",
    "eggplants": "Beringela", "garlic": "Alho", "ginger": "Gengibre", "green beans": "Feijão verde",
    "green grapes": "Uva branca", "green peppers": "Pimento verde", "guavas": "Goiaba",
    "kiwis": "Kiwi", "lemons": "Limão", "lettuce": "Alface", "limes": "Lima", "mangoes": "Manga",
    "melons": "Melão", "nectarines": "Nectarina", "onions": "Cebola", "oranges": "Laranja",
    "papayas": "Papaia", "passion fruits": "Maracujá", "peaches": "Pêssego", "pears": "Pera",
    "pineapples": "Ananás", "potatoes": "Batata", "pumpkins": "Abóbora", "red cabbages": "Couve roxa",
    "red grapes": "Uva vermelha", "red onions": "Cebola roxa", "red peppers": "Pimento vermelho",
    "shallots": "Chalota", "strawberries": "Morango", "sweet potatoes": "Batata-doce",
    "tomatoes": "Tomate", "watermelons": "Melancia", "zucchini": "Curgete",
}


def _camera_images(camera_dir, per_camera, image_name):
    """Return the images to use for one camera folder, sorted by name (= timestamp)."""
    if not camera_dir.is_dir():
        return []
    if image_name is not None:
        path = camera_dir / image_name
        return [path] if path.is_file() else []
    images = sorted(
        p for p in camera_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    return images[:1] if per_camera == "first" else images


def _quad(coords):
    return [[coords[k][0], coords[k][1]] for k in CORNER_KEYS]


def _bbox_by_excess(quad):
    """Smallest axis-aligned box containing all four corners: [x0, y0, x1, y1]."""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return [min(xs), min(ys), max(xs), max(ys)]


def _square_window(bbox, side, width, height):
    """side x side window centred on the bbox, shifted inward to stay inside the image.

    Never shrinks. If the image is smaller than side in a dimension, the window starts at 0 and
    the missing part is black padding (Pillow fills out-of-image crop areas with black).
    """
    cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
    sx0, sy0 = cx - side // 2, cy - side // 2
    sx0 = max(0, min(sx0, width - side)) if width >= side else 0
    sy0 = max(0, min(sy0, height - side)) if height >= side else 0
    return [sx0, sy0, sx0 + side, sy0 + side]


def _class_name_pt(class_key):
    base = class_key[len(PACKAGED_PREFIX):] if class_key.startswith(PACKAGED_PREFIX) else class_key
    pt = PT_NAMES.get(base)
    if pt is None:
        return None
    return pt + PACKAGED_SUFFIX_PT if class_key.startswith(PACKAGED_PREFIX) else pt


def _build_registry(classes, example_images):
    example_images = example_images or {}
    for key in example_images:
        if key not in classes:
            log.warning("example_images: %r is not a class in classes.json, ignored", key)
    registry = []
    for class_key in sorted(classes):
        nome_pt = _class_name_pt(class_key)
        if nome_pt is None:
            log.warning("class %r has no Portuguese name, nome_pt=null", class_key)
        registry.append({
            "class_key": class_key,
            "nome_pt": nome_pt,
            "sam3_prompt": class_key,
            "exemplo": example_images.get(class_key),
        })
    return registry


def crop_planogram(planogram_path, dataset_dir, output_dir, classes_path="dataset/classes.json",
                   per_camera="all", image_name=None, example_images=None):
    """Write a dataset of square crops (PNG), quad masks (uint8 .npy, 0/1) and class-registry references.

    Each dataset.jsonl line is {image, mask, class_key, product_id, exemplo}; exemplo is null unless
    example_images has a path for that class.

    Pass 1 computes one global side (the largest bbox-by-excess dimension over every planogram
    area); pass 2 centres a side x side window on each area. Every crop and mask is exactly
    side x side. Output: <output_dir>/images, masks, classes.json (registry) and dataset.jsonl.
    per_camera="all" uses every image, "first" the earliest per camera; image_name picks that exact
    file per camera and takes precedence. Returns a summary dict.
    """
    if per_camera not in ("all", "first"):
        raise ValueError(f"per_camera must be 'all' or 'first', got {per_camera!r}")

    planogram_path, dataset_dir, output_dir = Path(planogram_path), Path(dataset_dir), Path(output_dir)
    images_root = dataset_dir / "train" if (dataset_dir / "train").is_dir() else dataset_dir

    with open(planogram_path) as f:
        planogram = json.load(f)
    with open(classes_path) as f:
        classes = json.load(f)
    product_to_class = {}
    for class_key, product_ids in classes.items():
        for pid in product_ids:
            product_to_class[str(pid)] = class_key

    # PASS 1: global side over EVERY area, before cropping anything.
    side, total_areas = 0, 0
    for category_data in planogram.values():
        for camera_data in category_data["cameras"].values():
            for area in camera_data["products"]:
                x0, y0, x1, y1 = _bbox_by_excess(_quad(area["image_coordinates"]))
                side = max(side, x1 - x0, y1 - y0)
                total_areas += 1
    if side <= 0:
        raise ValueError("planogram has no areas with a positive size")
    print(f"global square side: {side}px (max over all {total_areas} planogram areas)")

    registry = _build_registry(classes, example_images)
    registry_keys = {c["class_key"] for c in registry}
    exemplo_by_class = {c["class_key"]: c["exemplo"] for c in registry}

    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "masks").mkdir(parents=True, exist_ok=True)

    samples, skipped, cameras_without_image, null_class = [], [], [], []

    # PASS 2: one square crop + mask + sample per area per image.
    for category_data in planogram.values():
        for camera_id, camera_data in category_data["cameras"].items():
            areas = camera_data["products"]
            images = _camera_images(images_root / camera_id, per_camera, image_name)
            if not images:
                log.warning("camera %s: no image found in %s, skipping %d areas",
                            camera_id, images_root / camera_id, len(areas))
                cameras_without_image.append(camera_id)
                continue

            for image_path in images:
                timestamp = image_path.stem
                with Image.open(image_path) as img:
                    img = img.convert("RGB")
                    width, height = img.size
                    for area in areas:
                        area_id = area["area_id"]
                        quad = _quad(area["image_coordinates"])
                        bbox = _bbox_by_excess(quad)
                        if (min(width, bbox[2]) - max(0, bbox[0]) <= 0
                                or min(height, bbox[3]) - max(0, bbox[1]) <= 0):
                            reason = f"degenerate box {bbox}: no overlap with the {width}x{height} image"
                            log.warning("area %s (%s): skipped, %s", area_id, image_path, reason)
                            skipped.append({"area_id": area_id, "camera_id": camera_id,
                                            "source_image": str(image_path), "reason": reason})
                            continue

                        square = _square_window(bbox, side, width, height)
                        crop = img.crop(tuple(square))  # out-of-image parts are black padding
                        mask = Image.new("L", (side, side), 0)
                        local_quad = [(x - square[0], y - square[1]) for x, y in quad]
                        ImageDraw.Draw(mask).polygon(local_quad, fill=255)
                        mask = (np.asarray(mask) > 0).astype(np.uint8)  # 0 background, 1 mask
                        assert crop.size == (side, side) and mask.shape == (side, side), \
                            "crop and mask must be exactly side x side"

                        stem = f"{area_id}__{camera_id}__{timestamp}"
                        crop.save(output_dir / "images" / f"{stem}.png")
                        np.save(output_dir / "masks" / f"{stem}.npy", mask)

                        product_id = str(area["product_id"])
                        class_key = product_to_class.get(product_id)
                        if class_key is None:
                            log.warning("area %s: product_id %s is not in %s, class_key=null",
                                        area_id, product_id, classes_path)
                            null_class.append(product_id)
                        assert class_key is None or class_key in registry_keys
                        samples.append({
                            "image": f"images/{stem}.png",
                            "mask": f"masks/{stem}.npy",
                            "class_key": class_key,
                            "product_id": product_id,
                            "exemplo": exemplo_by_class.get(class_key),
                        })

    with open(output_dir / "classes.json", "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(output_dir / "dataset.jsonl", "w") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    summary = {
        "side": side,
        "areas_in_planogram": total_areas,
        "samples_written": len(samples),
        "class_key_null": sorted(set(null_class)),
        "areas_skipped": len(skipped),
        "skipped": skipped,
        "cameras_without_image": cameras_without_image,
    }
    print(f"{len(samples)} samples written")
    print(f"{len(set(null_class))} product_ids with class_key=null"
          + (f": {', '.join(sorted(set(null_class)))}" if null_class else ""))
    reasons = Counter(s["reason"].split(" box")[0] for s in skipped)
    print(f"{len(skipped)} areas skipped" + (f" ({dict(reasons)})" if skipped else ""))
    for s in skipped:
        print(f"  - {s['area_id']} @ {s['source_image']}: {s['reason']}")
    print(f"{len(cameras_without_image)} cameras without an image"
          + (f": {', '.join(cameras_without_image)}" if cameras_without_image else ""))
    return summary

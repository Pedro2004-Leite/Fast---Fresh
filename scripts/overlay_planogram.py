"""Draw planogram areas (caramel-yellow overlay) with product info on camera images.

Usage:
    python3 scripts/overlay_planogram.py                      # one sample image
    python3 scripts/overlay_planogram.py --camera 6383 --image 1751001156.jpg
    python3 scripts/overlay_planogram.py --all                # whole train set
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"
OUT = ROOT / "overlay" / "planogram_regions"

CARAMEL = (232, 160, 32)
FONT_BOLD = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/liberation/LiberationMono-Bold.ttf"
CORNERS = ["top_left", "top_right", "bottom_right", "bottom_left"]
SHORT = {"top_left": "TL", "top_right": "TR", "bottom_right": "BR", "bottom_left": "BL"}


def load_planogram():
    with open(DATASET / "planogram.json") as f:
        return json.load(f)["Frutas e Legumes"]["cameras"]


def wrap(d, text, font, width):
    out, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if cur and d.textlength(t, font=font) > width:
            out.append(cur)
            cur = word
        else:
            cur = t
    return out + [cur]


def draw_overlay(img_path, products, out_path):
    img = Image.open(img_path).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for p in products:
        c = p["image_coordinates"]
        pts = [tuple(c[k]) for k in CORNERS]
        d.polygon(pts, fill=CARAMEL + (95,))
        d.line(pts + [pts[0]], fill=CARAMEL + (255,), width=2)

        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        # usable text box: narrowest horizontal extent, clamped to the visible image
        left = max(max(c["top_left"][0], c["bottom_left"][0]), 0) + 3
        right = min(min(c["top_right"][0], c["bottom_right"][0]), img.width) - 3
        top = max(max(c["top_left"][1], c["top_right"][1]), 0) + 2
        bottom = min(min(c["bottom_left"][1], c["bottom_right"][1]), img.height) - 2
        bw, bh = right - left, bottom - top

        coord_txt = " ".join(f"{SHORT[k]}({c[k][0]},{c[k][1]})" for k in CORNERS)
        chosen = None
        for size in range(13, 6, -1):
            ft = ImageFont.truetype(FONT_BOLD, size)
            fm = ImageFont.truetype(FONT_MONO, max(size - 3, 6))
            lines = [(p["area_id"], ft)]
            lines += [(t, ft) for t in wrap(d, p["product_name"], ft, bw)]
            lines += [(f"id {p['product_id']}", fm)]
            lines += [(t, fm) for t in wrap(d, coord_txt, fm, bw)]
            heights = [f.size + 2 for _, f in lines]
            if sum(heights) <= bh and all(d.textlength(t, font=f) <= bw for t, f in lines):
                chosen = (lines, heights)
                break
            chosen = (lines, heights)  # smallest size fallback
        lines, heights = chosen
        y = top + max((bh - sum(heights)) / 2, 0)
        for (t, f), lh in zip(lines, heights):
            col = (255, 255, 255, 255) if f.path == FONT_MONO else (255, 214, 110, 255)
            d.text((left, y), t, font=f, fill=col, stroke_width=1, stroke_fill=(0, 0, 0, 255))
            y += lh

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(img, layer).convert("RGB").save(out_path, quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", default="6215")
    ap.add_argument("--image", default=None, help="file name; defaults to first image of the camera")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    cams = load_planogram()
    if a.all:
        todo = [(cam, p) for cam in cams for p in sorted((DATASET / "train" / cam).glob("*.jpg"))]
    else:
        cam_dir = DATASET / "train" / a.camera
        img = cam_dir / a.image if a.image else sorted(cam_dir.glob("*.jpg"))[0]
        todo = [(a.camera, img)]

    for cam, path in todo:
        out = OUT / cam / path.name
        draw_overlay(path, cams[cam]["products"], out)
        print(out)


if __name__ == "__main__":
    main()

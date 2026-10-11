"""Figuras para o slide de prompt engineering (juntam overlays e crops já gerados)."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "slide_prompt_engineering"
OV = ROOT / "overlay"
CROPS = ROOT / "output" / "crops" / "images"
S = 2  # upscale
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
INK, MUTED, PAPER = (30, 33, 36), (110, 115, 120), (255, 255, 255)
GOOD, BAD = (30, 150, 70), (200, 40, 50)


def font(n: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, n)


def load(p: Path, size: int = 292 * S) -> Image.Image:
    return Image.open(p).convert("RGB").resize((size, size), Image.LANCZOS)


def panel(canvas: Image.Image, img: Image.Image, x: int, y: int, title: str, sub: str = "", color=INK) -> None:
    d = ImageDraw.Draw(canvas)
    d.text((x, y), title, fill=color, font=font(30))
    if sub:
        d.text((x, y + 38), sub, fill=MUTED, font=font(24))
    top = y + (80 if sub else 46)
    canvas.paste(img, (x, top))
    d.rectangle([x, top, x + img.width, top + img.height], outline=color, width=6)


def row(title_sub: list[tuple[Image.Image, str, str, tuple]], name: str, gap: int = 40) -> None:
    w = sum(i.width for i, *_ in title_sub) + gap * (len(title_sub) + 1)
    h = title_sub[0][0].height + 80 + 2 * gap
    c = Image.new("RGB", (w, h), PAPER)
    x = gap
    for img, t, s, col in title_sub:
        panel(c, img, x, gap, t, s, col)
        x += img.width + gap
    c.save(OUT / name)
    print(name, c.size)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. Saco de uvas: só texto vs texto + exemplo
    c = "6462_4__6462__1751020617.png"
    row([
        (load(CROPS / c), "Prateleira", "uvas brancas em sacos de papel", INK),
        (load(OV / "sam3_textonly_plural/green grapes" / c), 'Só texto: "green grapes"', "1 de 10 sacos", BAD),
        (load(OV / "sam3_visual/text_visual/21307" / c), "Texto + imagem de exemplo", "10 de 10 sacos", GOOD),
    ], "1_saco_de_uvas.png")

    # 2. Embalados: só texto vs texto + exemplo
    c = "6462_5__6462__1751020617.png"
    row([
        (load(CROPS / c), "Prateleira", "uvas embaladas (barquetas)", INK),
        (load(OV / "sam3_textonly_plural/packaged green grapes" / c), 'Só texto: "packaged green grapes"', "nenhuma deteção", BAD),
        (load(OV / "sam3_visual/text_visual/19032" / c), "Texto + imagem de exemplo", "14 deteções, uma por embalagem", GOOD),
    ], "2_embalados.png")

    # 3. Maçã: 1.ª iteração (genérica) -> 2.ª iteração (por variedade, com exemplo do dataset)
    ex = json.load(open(ROOT / "examples_by_product.json"))
    c = "6373_1__6373__1751032836.png"
    tiles = []
    for area, label in (("13702", '"red apples"'), ("11919", '"green apples"'), ("32170", '"brown apples" (reineta)')):
        e = ex[area]
        im = Image.open(CROPS / Path(e["image"]).name).convert("RGB")
        x0, y0, x1, y1 = e["box"]
        pad = 12
        im = im.crop((max(x0 - pad, 0), max(y0 - pad, 0), x1 + pad, y1 + pad)).resize((292 * S, 292 * S), Image.LANCZOS)
        tiles.append((im, label, "2.ª iteração: prompt por cor", GOOD))
    row([(load(OV / "sam3_textonly_plural/apples" / c), '"apples"', "1.ª iteração: cores misturadas", BAD)] + tiles, "3_macas_iteracoes.png")


if __name__ == "__main__":
    main()

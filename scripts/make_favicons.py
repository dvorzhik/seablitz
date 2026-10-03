"""Генерация PNG/ICO фавиконов SeaBlitz (прицел + синий корабль).

Запуск:  python scripts/make_favicons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static"
SS = 8  # суперсэмплинг для гладких краёв
BASE = 64.0

BLACK = (10, 10, 10, 255)
BLUE = (20, 84, 138, 255)


def draw_icon(size: int) -> Image.Image:
    s = int(size * SS)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = s / BASE

    def sc(v: float) -> float:
        return v * k

    lw = max(1, round(4.5 * k))   # толщина прицела
    tw = max(1, round(3.0 * k))   # толщина рисок
    r = 22.5

    d.ellipse([sc(32 - r), sc(32 - r), sc(32 + r), sc(32 + r)], outline=BLACK, width=lw)
    d.line([sc(6), sc(32), sc(58), sc(32)], fill=BLACK, width=lw)
    d.line([sc(32), sc(6), sc(32), sc(58)], fill=BLACK, width=lw)

    for x in (20, 44):
        d.line([sc(x), sc(27), sc(x), sc(37)], fill=BLACK, width=tw)
    for y in (20, 44):
        d.line([sc(27), sc(y), sc(37), sc(y)], fill=BLACK, width=tw)

    d.polygon(
        [(sc(21), sc(37)), (sc(43), sc(37)), (sc(39), sc(42)), (sc(25), sc(42))],
        fill=BLUE,
    )
    d.rectangle([sc(28.5), sc(32), sc(35.5), sc(38)], fill=BLUE)
    d.rectangle([sc(30), sc(29), sc(34), sc(32.5)], fill=BLUE)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    for size in (32, 48, 180, 192):
        draw_icon(size).save(OUT / f"favicon-{size}.png")
    draw_icon(64).save(
        OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
    )
    print("favicons written to", OUT)


if __name__ == "__main__":
    main()

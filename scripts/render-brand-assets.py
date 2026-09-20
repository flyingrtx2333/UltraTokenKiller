"""Render deterministic transparent PNG exports for the UTK brand mark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "public" / "brand"
OFF_WHITE = "#E9F0F4"
MINT = "#38D4A7"


def _draw_mark(canvas: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Draw the 64-unit production mark into box using supersampled geometry."""
    left, top, width, height = box
    scale = min(width, height) / 64
    ox = left + (width - 64 * scale) / 2
    oy = top + (height - 64 * scale) / 2
    draw = ImageDraw.Draw(canvas)

    def point(x: float, y: float) -> tuple[float, float]:
        return ox + x * scale, oy + y * scale

    draw.polygon(
        [point(x, y) for x, y in [(20, 6), (5, 18), (5, 46), (20, 58), (20, 49), (13, 43), (13, 21), (20, 15)]],
        fill=OFF_WHITE,
    )
    draw.polygon(
        [point(x, y) for x, y in [(44, 6), (59, 18), (59, 46), (44, 58), (44, 49), (51, 43), (51, 21), (44, 15)]],
        fill=MINT,
    )

    def rect(x1: float, y1: float, x2: float, y2: float, fill: str) -> None:
        draw.rectangle((*point(x1, y1), *point(x2, y2)), fill=fill)

    rect(22, 23, 25, 41, OFF_WHITE)
    rect(27, 27, 29, 37, OFF_WHITE)
    rect(39, 23, 42, 41, MINT)
    rect(35, 27, 37, 37, MINT)
    rect(31.25, 25, 32.75, 42, MINT)
    rect(30.25, 22, 33.75, 26, MINT)


def render_icon(size: int) -> None:
    supersample = 8
    canvas = Image.new("RGBA", (size * supersample, size * supersample), (0, 0, 0, 0))
    _draw_mark(canvas, (0, 0, size * supersample, size * supersample))
    canvas.resize((size, size), Image.Resampling.LANCZOS).save(OUTPUT / f"utk-icon-{size}.png", optimize=True)


def render_lockup() -> None:
    supersample = 4
    width, height = 860, 160
    canvas = Image.new("RGBA", (width * supersample, height * supersample), (0, 0, 0, 0))
    _draw_mark(canvas, (16 * supersample, 16 * supersample, 128 * supersample, 128 * supersample))
    candidates = (
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    font_path = next((path for path in candidates if path.is_file()), None)
    font = (ImageFont.truetype(str(font_path), 62 * supersample)
            if font_path else ImageFont.load_default(size=62 * supersample))
    draw = ImageDraw.Draw(canvas)
    x, y = 180 * supersample, 43 * supersample
    for text, color in [("Ultra", OFF_WHITE), ("Token", MINT), ("Killer", OFF_WHITE)]:
        draw.text((x, y), text, font=font, fill=color)
        x += draw.textlength(text, font=font)
    canvas.resize((width, height), Image.Resampling.LANCZOS).save(OUTPUT / "utk-lockup-860.png", optimize=True)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for export_size in (16, 32, 64, 256, 512, 1024):
        render_icon(export_size)
    render_lockup()

"""Conservative local compression for inline raster images."""
from __future__ import annotations

import base64
import io
import re


DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\r\n]+)$", re.I)
DETAIL_TASK = re.compile(
    r"(?:ocr|read (?:the )?text|pixel|exact detail|small text|diagram|schematic|screenshot|code)|"
    r"(?:识字|文字|逐字|像素|精确细节|小字|图表|流程图|截图|代码)", re.I)


def compress_data_url(value: str, query: str = "", aggressive: bool = False) -> str:
    if DETAIL_TASK.search(query):
        return value
    match = DATA_URL.fullmatch(value)
    if not match:
        return value
    try:
        raw = base64.b64decode(match[2], validate=True)
    except (ValueError, base64.binascii.Error):
        return value
    if len(raw) > 12 * 1024 * 1024:
        return value
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return value
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            if source.width * source.height > 40_000_000 or max(source.size) <= 2048:
                return value
            probe = source.convert("L")
            probe.thumbnail((256, 256))
            edges = probe.filter(ImageFilter.FIND_EDGES)
            histogram = edges.histogram()
            sharp = sum(histogram[48:]) / max(1, sum(histogram))
            # Dense edges usually indicate text, diagrams or screenshots.
            if sharp > .16:
                return value
            target = 1024 if aggressive else 1600
            image = source.copy()
            image.thumbnail((target, target))
            output = io.BytesIO()
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            if has_alpha:
                image.save(output, format="WEBP", quality=82, method=4)
                mime = "image/webp"
            else:
                image.convert("RGB").save(output, format="JPEG", quality=82, optimize=True)
                mime = "image/jpeg"
            encoded = output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        return value
    if len(encoded) >= len(raw) * .85:
        return value
    return f"data:{mime};base64," + base64.b64encode(encoded).decode("ascii")

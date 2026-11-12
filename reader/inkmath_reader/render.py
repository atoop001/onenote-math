"""Draw strokes as a black-on-white grayscale image, scaled to a fixed height."""
from PIL import Image, ImageDraw

from .ink import NoInk

MAX_WIDTH_PX = 2048
MIN_WIDTH_PX = 30   # texteller MIN_WIDTH


def render(strokes, height_px: int = 256, pad_px: int = 16, line_px: int = 3) -> Image.Image:
    pts = [p for s in strokes for p in s]
    if not pts:
        raise NoInk("no ink points")
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    w = max(max(p[0] for p in pts) - x0, 1e-6)
    h = max(max(p[1] for p in pts) - y0, 1e-6)
    inner = height_px - 2 * pad_px
    scale = min(inner / h, (MAX_WIDTH_PX - 2 * pad_px) / w)
    width_px = max(int(round(w * scale)) + 2 * pad_px, MIN_WIDTH_PX)
    xoff = (width_px - w * scale) / 2 if w * scale + 2 * pad_px < MIN_WIDTH_PX else pad_px
    yoff = pad_px + (inner - h * scale) / 2  # center short content vertically
    img = Image.new("L", (width_px, height_px), 255)
    draw = ImageDraw.Draw(img)
    for s in strokes:
        if not s:
            continue
        xy = [(xoff + (x - x0) * scale, yoff + (y - y0) * scale) for x, y in s]
        if len(xy) == 1:
            xy = xy * 2
        draw.line(xy, fill=0, width=line_px, joint="curve")
    return img

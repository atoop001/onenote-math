"""Draw strokes as a black-on-white PNG, scaled to a fixed height."""
from PIL import Image, ImageDraw

MAX_WIDTH_PX = 2048


def render_png(strokes, path, height_px: int = 256, pad_px: int = 16, width_px_line: int = 3) -> None:
    pts = [p for s in strokes for p in s]
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    w = max(max(p[0] for p in pts) - x0, 1e-6)
    h = max(max(p[1] for p in pts) - y0, 1e-6)
    inner = height_px - 2 * pad_px
    scale = min(inner / h, (MAX_WIDTH_PX - 2 * pad_px) / w)
    width_px = int(round(w * scale)) + 2 * pad_px
    yoff = pad_px + (inner - h * scale) / 2  # center short content vertically
    img = Image.new("L", (width_px, height_px), 255)
    draw = ImageDraw.Draw(img)
    for s in strokes:
        xy = [(pad_px + (x - x0) * scale, yoff + (y - y0) * scale) for x, y in s]
        if len(xy) == 1:
            xy = xy * 2
        draw.line(xy, fill=0, width=width_px_line, joint="curve")
    img.save(path)

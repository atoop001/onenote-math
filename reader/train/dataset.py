"""Tuning samples (the user's tune pages + saved corrections), stroke-level augmentation, rendering."""
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from inkmath_reader import corrections
from inkmath_reader.ink import Stroke
from inkmath_reader.render import render


@dataclass
class Sample:
    id: str
    strokes: list[Stroke]
    latex: str


def load_tune(ink_dir: Path, prompts: Path, manifest: str = "tune_manifest.json") -> list[Sample]:
    """Samples whose id is in the manifest's `ok` list and has both ink and a prompt."""
    ink_dir = Path(ink_dir)
    ok = json.loads((ink_dir / manifest).read_text(encoding="utf-8"))["ok"]
    truth = {p["id"]: p["latex"] for p in json.loads(Path(prompts).read_text(encoding="utf-8"))}
    out = []
    for sid in ok:
        f = ink_dir / f"{sid}.json"
        if sid in truth and f.exists():
            strokes = [[tuple(pt) for pt in s] for s in json.loads(f.read_text(encoding="utf-8"))]
            out.append(Sample(sid, strokes, truth[sid]))
    return out


def load_corrections(dir: Path) -> list[Sample]:
    return [Sample(f"c{i:04d}", strokes, latex) for i, (strokes, latex) in enumerate(corrections.load(dir))]


def augment(strokes: list[Stroke], rng: random.Random) -> list[Stroke]:
    """Per-axis scale U(0.9,1.1), rotation U(-3°,3°), x-shear U(-0.1,0.1), point jitter N(0, 0.3 DIP)."""
    sx, sy = rng.uniform(0.9, 1.1), rng.uniform(0.9, 1.1)
    a = math.radians(rng.uniform(-3.0, 3.0))
    shear = rng.uniform(-0.1, 0.1)
    pts = [p for s in strokes for p in s]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    cos, sin = math.cos(a), math.sin(a)
    out = []
    for s in strokes:
        ns = []
        for x, y in s:
            x, y = (x - cx) * sx, (y - cy) * sy
            x = x + shear * y
            x, y = x * cos - y * sin, x * sin + y * cos
            ns.append((x + cx + rng.gauss(0, 0.3), y + cy + rng.gauss(0, 0.3)))
        out.append(ns)
    return out


def render_view(strokes: list[Stroke], rng: random.Random) -> Image.Image:
    """Render at height U(0.75,1.15)×256 with a 2-4 px line."""
    return render(strokes, height_px=int(round(256 * rng.uniform(0.75, 1.15))), line_px=rng.choice((2, 3, 4)))

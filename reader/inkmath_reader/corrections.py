"""Confirmed fixes, saved locally as training data (spec §6.3 "learning from corrections")."""
import json
import secrets
from datetime import datetime
from pathlib import Path

from .ink import Stroke


def save(dir: Path, strokes: list[Stroke], recognized: str, corrected: str) -> Path:
    dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)
    path = dir / f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}.json"
    data = {"strokes": [[list(p) for p in s] for s in strokes], "recognized": recognized, "corrected": corrected}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def load(dir: Path) -> list[tuple[list[Stroke], str]]:
    """(strokes, corrected LaTeX) for every saved correction, oldest first."""
    out = []
    for path in sorted(Path(dir).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(([[tuple(p) for p in s] for s in data["strokes"]], data["corrected"]))
    return out

"""Prompt sets the user hand-copies on the Surface (ground truth for scoring)."""
import json
from dataclasses import dataclass
from pathlib import Path

AREAS = ("algebra", "precalc", "calc1", "calc2")


@dataclass(frozen=True)
class Prompt:
    id: str
    area: str
    display: str
    latex: str


def load_prompts(path) -> list[Prompt]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    prompts = [Prompt(**item) for item in raw]
    for p in prompts:
        if p.area not in AREAS:
            raise ValueError(f"{p.id}: unknown area {p.area!r}")
    return prompts

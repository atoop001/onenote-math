"""Find ink on a OneNote page and group it under the prompt it answers."""
import base64
import xml.etree.ElementTree as ET

from inkspike.onenote_io import NS


class NoInkError(RuntimeError):
    pass


def _q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def _pos(el):
    p = el.find(_q("Position"))
    return (float(p.get("x")), float(p.get("y"))) if p is not None else None


def ink_items(page_xml: str) -> list[tuple[float, float, bytes]]:
    """(page x, page y, ISF bytes) for every InkDrawing and InkWord on the page."""
    root = ET.fromstring(page_xml)
    items = []
    for d in root.iter(_q("InkDrawing")):
        pos, data = _pos(d), d.find(_q("Data"))
        if pos and data is not None and data.text:
            items.append((*pos, base64.b64decode(data.text)))
    for outline in root.iter(_q("Outline")):
        opos = _pos(outline) or (0.0, 0.0)
        for w in outline.iter(_q("InkWord")):
            data = w.find(_q("Data"))
            if data is not None and data.text:
                items.append((*(_pos(w) or opos), base64.b64decode(data.text)))
    return items


def assign_to_bands(items_y: list[float], tops: list[float]) -> list[int]:
    """Index of the nearest band top at or above each y; ink above band 0 goes to band 0."""
    out = []
    for y in items_y:
        above = [i for i, t in enumerate(tops) if t <= y]
        out.append(above[-1] if above else 0)
    return out


def build_manifest(assignments: dict[str, int]) -> dict:
    """assignments: prompt id -> number of ink items found under it."""
    return {"ok": [k for k, n in assignments.items() if n > 0],
            "missing": [k for k, n in assignments.items() if n == 0]}


def check_page_has_ink(title: str, items: list) -> None:
    if not items:
        raise NoInkError(
            f"'{title}' has no ink on this computer. Either it hasn't synced yet "
            f"(open the notebook in OneNote here and wait until it says synced) or it wasn't written."
        )

import xml.etree.ElementTree as ET

import pytest

from inkspike.onenote_io import NS, band_tops, build_prompt_page_xml
from inkspike.prompts import Prompt

P = [Prompt("T01", "calc2", "∫₀^π x sin x dx", r"\int_{0}^{\pi} x \sin x \, dx"),
     Prompt("T02", "algebra", "x² + 5x + 6", "x^2+5x+6")]


def test_page_xml_has_title_and_positioned_prompts():
    root = ET.fromstring(build_prompt_page_xml("{PAGE}", "Ink Math Test 1", P))
    assert root.find(f".//{{{NS}}}Title//{{{NS}}}T").text == "Ink Math Test 1"
    outlines = root.findall(f"{{{NS}}}Outline")
    ys = [float(o.find(f"{{{NS}}}Position").get("y")) for o in outlines]
    assert ys == band_tops(2)
    assert "T01. ∫₀^π x sin x dx" in ET.tostring(root, encoding="unicode")


def test_band_tops():
    assert band_tops(3) == [80.0, 220.0, 360.0]


@pytest.mark.onenote
def test_roundtrip_in_scratch_section():
    from inkspike.onenote_io import OneNote
    from pathlib import Path
    on = OneNote()
    nb_path = Path(__file__).resolve().parents[2] / "data" / "scratch-notebook"
    nb_path.mkdir(parents=True, exist_ok=True)
    nb = on.open_notebook(str(nb_path))
    try:
        sec = on.ensure_section(nb, "Ink Math Spike Scratch")
        assert on.ensure_section(nb, "Ink Math Spike Scratch") == sec
        pid = on.create_page(sec, lambda page_id: build_prompt_page_xml(page_id, "scratch", P))
        try:
            assert "T02. x² + 5x + 6" in on.get_page_xml(pid, binary=False)
            assert ("scratch", pid) in on.pages_in_section(sec)
        finally:
            on.delete_page(pid)
    finally:
        on.close_notebook(nb)

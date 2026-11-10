from pathlib import Path

import pytest

from inkspike.extract import NoInkError, assign_to_bands, build_manifest, check_page_has_ink, ink_items

FIX = Path(__file__).parent / "fixtures"


def test_inkword_and_inkdrawing_both_found():
    for f in ("page_inkword.xml", "page_inkdrawing.xml"):
        assert len(ink_items((FIX / f).read_text(encoding="utf-8"))) >= 1


def test_inkword_inherits_outline_position():
    items = ink_items((FIX / "page_inkword.xml").read_text(encoding="utf-8"))
    assert (items[0][0], items[0][1]) == (40.0, 230.0)


def test_assign_to_bands_nearest_above():
    assert assign_to_bands([90, 219, 221, 10], [80.0, 220.0, 360.0]) == [0, 0, 1, 0]


def test_manifest_lists_missing():
    m = build_manifest({"T01": 3, "T02": 0, "T03": 5})
    assert m == {"ok": ["T01", "T03"], "missing": ["T02"]}


def test_zero_ink_page_raises():
    with pytest.raises(NoInkError, match=r"(?s)Ink Math Tune 2.*synced"):
        check_page_has_ink("Ink Math Tune 2", [])
    check_page_has_ink("Ink Math Tune 1", [(0.0, 0.0, b"x")])

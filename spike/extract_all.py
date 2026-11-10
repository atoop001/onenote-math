"""Pull the handwritten samples off the prompt pages.

Usage: python extract_all.py --set test|tune [--notebook math-writing-test]
Writes data/ink/<id>.json (strokes), data/ink/<id>.png and data/ink/<set>_manifest.json.
A page with no ink is reported loudly (exit code 1); its prompts are listed as missing.
"""
import argparse
import json
import sys
from pathlib import Path

from inkspike.extract import NoInkError, assign_to_bands, build_manifest, check_page_has_ink, ink_items
from inkspike.isf import decode_isf
from inkspike.onenote_io import OneNote, band_tops
from inkspike.prompts import load_prompts
from inkspike.render import render_png

ROOT = Path(__file__).resolve().parents[1]
PER_PAGE = 10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=["test", "tune"])
    ap.add_argument("--notebook", default="math-writing-test")
    args = ap.parse_args()
    label = args.set.capitalize()

    prompts = load_prompts(ROOT / "samples" / f"prompts_{args.set}.json")
    on = OneNote()
    nb = dict(on.list_notebooks())[args.notebook]
    section = on.ensure_section(nb, f"Ink Math {label}")
    pages = dict(on.pages_in_section(section))
    out = ROOT / "data" / "ink"
    out.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {p.id: 0 for p in prompts}
    problems = []
    for k in range(1, len(prompts) // PER_PAGE + 1):
        title = f"Ink Math {label} {k}"
        chunk = prompts[(k - 1) * PER_PAGE:k * PER_PAGE]
        items = ink_items(on.get_page_xml(pages[title], binary=True)) if title in pages else []
        try:
            check_page_has_ink(title, items)
        except NoInkError as e:
            problems.append(str(e))
            continue
        bands = assign_to_bands([y for _, y, _ in items], band_tops(len(chunk)))
        grouped: dict[int, list] = {}
        for (_, _, data), b in zip(items, bands):
            grouped.setdefault(b, []).extend(decode_isf(data))
        for i, p in enumerate(chunk):
            strokes = grouped.get(i, [])
            counts[p.id] = len(strokes)
            if strokes:
                (out / f"{p.id}.json").write_text(json.dumps(strokes), encoding="utf-8")
                render_png(strokes, out / f"{p.id}.png")

    manifest = build_manifest(counts)
    (out / f"{args.set}_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"ok: {len(manifest['ok'])}, missing: {len(manifest['missing'])}"
          + (f" ({', '.join(manifest['missing'])})" if manifest["missing"] else ""))
    for msg in problems:
        print(f"WARNING: {msg}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

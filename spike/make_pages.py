"""Create the handwriting prompt pages in a OneNote notebook.

Usage: python make_pages.py --notebook "<notebook name>"
"""
import argparse
import sys
from pathlib import Path

from inkspike.onenote_io import OneNote, build_prompt_page_xml
from inkspike.prompts import load_prompts

ROOT = Path(__file__).resolve().parents[1]
SETS = {
    "Test": ROOT / "samples" / "prompts_test.json",
    "Tune": ROOT / "samples" / "prompts_tune.json",
}
PER_PAGE = 10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", default="")
    args = ap.parse_args()

    on = OneNote()
    notebooks = dict(on.list_notebooks())
    if args.notebook not in notebooks:
        print("Pick a notebook with --notebook. Open notebooks on this computer:")
        for name in notebooks or ["(none open. Open the synced notebook in OneNote first.)"]:
            print(f"  {name}")
        return 1
    nb = notebooks[args.notebook]

    plan = []
    for label, path in SETS.items():
        section = on.ensure_section(nb, f"Ink Math {label}")
        if on.pages_in_section(section):
            print(f"Section 'Ink Math {label}' already has pages. Nothing created, so nothing is duplicated.")
            return 1
        plan.append((label, section, load_prompts(path)))

    created = 0
    for label, section, prompts in plan:
        for k in range(0, len(prompts), PER_PAGE):
            title = f"Ink Math {label} {k // PER_PAGE + 1}"
            chunk = prompts[k:k + PER_PAGE]
            on.create_page(section, lambda pid, t=title, c=chunk: build_prompt_page_xml(pid, t, c))
            created += 1
    print(f"Created {created} pages. On the Surface, open each page and write each problem in the space under it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

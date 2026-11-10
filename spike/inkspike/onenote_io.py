"""OneNote desktop access for the spike.

On the dev machine Office is 32-bit and Python is 64-bit, and 64-bit COM clients
cannot marshal OneNote's interface there. So every call runs inside the built-in
32-bit Windows PowerShell as a subprocess. Arguments go in and results come out
through UTF-8 temp files, which avoids console encoding problems.
"""
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://schemas.microsoft.com/office/onenote/2013/onenote"
ET.register_namespace("one", NS)

# OneNote enums
HS_SELF, HS_CHILDREN, HS_NOTEBOOKS, HS_SECTIONS, HS_PAGES = 0, 1, 2, 3, 4
CFT_NONE, CFT_NOTEBOOK, CFT_FOLDER, CFT_SECTION = 0, 1, 2, 3
PI_BASIC, PI_BINARY_DATA = 0, 1

PS32 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$on = New-Object -ComObject OneNote.Application
$a = [IO.File]::ReadAllText($env:INKSPIKE_ARGS, [Text.Encoding]::UTF8) | ConvertFrom-Json
$r = ''
"""
_POSTLUDE = r"""
[IO.File]::WriteAllText($env:INKSPIKE_OUT, [string]$r, (New-Object Text.UTF8Encoding $false))
"""

_BODIES = {
    "hierarchy": "[string]$x = ''; $on.GetHierarchy($a.start, [int]$a.scope, [ref]$x); $r = $x",
    "open": "[string]$id = ''; $on.OpenHierarchy($a.path, $a.rel, [ref]$id, [int]$a.cft); $r = $id",
    "new_page": "[string]$id = ''; $on.CreateNewPage($a.section, [ref]$id, 0); $r = $id",
    "update": "$on.UpdatePageContent($a.xml)",
    "content": "[string]$x = ''; $on.GetPageContent($a.page, [ref]$x, [int]$a.info); $r = $x",
    "delete": "$on.DeleteHierarchy($a.id)",
    "close": "$on.CloseNotebook($a.id)",
}


class OneNoteError(RuntimeError):
    pass


def _q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def band_tops(n: int, top: float = 80.0, gap: float = 140.0) -> list[float]:
    return [top + i * gap for i in range(n)]


def build_prompt_page_xml(page_id: str, title: str, prompts, top: float = 80.0, gap: float = 140.0) -> str:
    page = ET.Element(_q("Page"), {"ID": page_id})
    t = ET.SubElement(page, _q("Title"))
    ET.SubElement(ET.SubElement(t, _q("OE")), _q("T")).text = title
    for p, y in zip(prompts, band_tops(len(prompts), top, gap)):
        o = ET.SubElement(page, _q("Outline"))
        ET.SubElement(o, _q("Position"), {"x": "36", "y": f"{y}", "z": "0"})
        ET.SubElement(o, _q("Size"), {"width": "520", "height": "20"})
        oe = ET.SubElement(ET.SubElement(o, _q("OEChildren")), _q("OE"))
        ET.SubElement(oe, _q("T")).text = f"{p.id}. {p.display}"
    return ET.tostring(page, encoding="unicode")


class OneNote:
    def _call(self, op: str, **args) -> str:
        with tempfile.TemporaryDirectory() as d:
            script, arg_path, out_path = Path(d, "op.ps1"), Path(d, "args.json"), Path(d, "out.txt")
            script.write_text(_PRELUDE + _BODIES[op] + _POSTLUDE, encoding="utf-8-sig")
            arg_path.write_text(json.dumps(args), encoding="utf-8")
            env = dict(os.environ, INKSPIKE_ARGS=str(arg_path), INKSPIKE_OUT=str(out_path))
            proc = subprocess.run(
                [str(PS32), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                env=env, capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0 or not out_path.exists():
                raise OneNoteError(f"OneNote call '{op}' failed: {proc.stderr.strip() or proc.stdout.strip()}")
            return out_path.read_text(encoding="utf-8")

    def _hierarchy(self, start: str, scope: int) -> ET.Element:
        return ET.fromstring(self._call("hierarchy", start=start, scope=scope))

    def list_notebooks(self) -> list[tuple[str, str]]:
        root = self._hierarchy("", HS_NOTEBOOKS)
        return [(nb.get("name"), nb.get("ID")) for nb in root.iter(_q("Notebook"))]

    def open_notebook(self, path: str) -> str:
        """Open (creating if needed) a notebook at a local folder path."""
        return self._call("open", path=str(path), rel="", cft=CFT_NOTEBOOK)

    def close_notebook(self, notebook_id: str) -> None:
        self._call("close", id=notebook_id)

    def ensure_section(self, notebook_id: str, name: str) -> str:
        root = self._hierarchy(notebook_id, HS_SECTIONS)
        for s in root.iter(_q("Section")):
            if s.get("name") == name:
                return s.get("ID")
        return self._call("open", path=f"{name}.one", rel=notebook_id, cft=CFT_SECTION)

    def pages_in_section(self, section_id: str) -> list[tuple[str, str]]:
        root = self._hierarchy(section_id, HS_PAGES)
        return [(p.get("name"), p.get("ID")) for p in root.iter(_q("Page"))]

    def create_page(self, section_id: str, xml_builder) -> str:
        page_id = self._call("new_page", section=section_id)
        self._call("update", xml=xml_builder(page_id))
        return page_id

    def get_page_xml(self, page_id: str, binary: bool) -> str:
        return self._call("content", page=page_id, info=PI_BINARY_DATA if binary else PI_BASIC)

    def delete_page(self, page_id: str) -> None:
        self._call("delete", id=page_id)

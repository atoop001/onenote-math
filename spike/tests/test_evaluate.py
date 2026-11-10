import json

from evaluate import run_eval
from inkspike.prompts import Prompt


class FakeRec:
    name = "fake"

    def __init__(self, answers):
        self.answers = answers

    def recognize(self, png_path):
        return self.answers[png_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1][:-4]]


def test_run_eval_skips_missing_and_writes_report(tmp_path):
    prompts = [Prompt("T01", "algebra", "x²", "x^2"), Prompt("T02", "calc1", "x³", "x^3"),
               Prompt("T03", "calc2", "∫x", r"\int x")]
    ink = tmp_path / "ink"
    ink.mkdir()
    (ink / "test_manifest.json").write_text(json.dumps({"ok": ["T01", "T02"], "missing": ["T03"]}))
    rec = FakeRec({"T01": "x^{2}", "T02": "x2"})
    out = tmp_path / "reports" / "fake.md"
    summary = run_eval(rec, prompts, ink, "test", out)
    assert summary["n"] == 2 and summary["zero_rate"] == 0.5
    text = out.read_text(encoding="utf-8")
    assert "T02" in text and "T03" in text  # worst list and missing list
    assert "structural: 1" in text and "symbol: 0" in text

"""Reader service protocol, corrections store and weight choice (synthetic ink only)."""
import base64
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import READER, REPO
from inkmath_reader.recognize import RawReading, TokenStep


def _ink_b64():
    from inkmath_reader.ink import encode_strokes
    strokes = [[(10 + i, 10 + i) for i in range(20)], [(40, 10), (40, 40)]]
    return base64.b64encode(encode_strokes(strokes)).decode()


class FakeRecognizer:
    name = "texteller"

    def __init__(self, latex="3x-7=11", fail=False):
        self.latex, self.fail, self.calls = latex, fail, 0

    def read(self, img):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        steps = [TokenStep(c, 0.5 if c == "7" else 0.99, []) for c in self.latex]
        return RawReading(self.latex, self.latex, steps)


@pytest.fixture
def server(tmp_path):
    from inkmath_reader.server import Server
    return Server(FakeRecognizer(), tmp_path, 0.85)


def test_read_ok_returns_latex_symbols_snippet_and_timings(server, tmp_path):
    r = server.handle({"id": "r1", "op": "read", "ink": [_ink_b64()]})
    assert r["id"] == "r1" and r["status"] == "ok" and r["latex"] == "3x-7=11"
    assert [s["text"] for s in r["symbols"]] == list("3x-7=11")
    seven = r["symbols"][3]
    assert seven["low"] is True and seven["start"] == 3 and seven["end"] == 4 and len(seven["alternatives"]) <= 3
    assert r["snippet"] == str(tmp_path / "selections" / "last.png") and os.path.exists(r["snippet"])
    assert r["model"] == "texteller" and set(r["ms"]) == {"ink", "model", "total"}
    json.dumps(r)


def test_no_ink_items_is_no_ink(server):
    for msg in ({"id": "a", "op": "read", "ink": []}, {"id": "a", "op": "read"}):
        r = server.handle(msg)
        assert r == {"id": "a", "status": "no_ink", "message": "Lasso some handwriting first."}


def test_empty_reading_is_reported(tmp_path):
    from inkmath_reader.server import Server
    r = Server(FakeRecognizer(latex=""), tmp_path, 0.85).handle({"id": "e", "op": "read", "ink": [_ink_b64()]})
    assert r == {"id": "e", "status": "empty", "message": "Couldn't read any math in this ink."}


def test_recognizer_exception_is_error_and_server_survives(tmp_path):
    from inkmath_reader.server import Server
    rec = FakeRecognizer(fail=True)
    s = Server(rec, tmp_path, 0.85)
    assert s.handle({"id": "x", "op": "read", "ink": [_ink_b64()]}) == \
        {"id": "x", "status": "error", "message": "Couldn't read this handwriting."}
    rec.fail = False
    assert s.handle({"id": "y", "op": "read", "ink": [_ink_b64()]})["status"] == "ok"


def test_bad_json_and_unknown_op_are_bad_request(server):
    assert server.handle_line("{not json") == {"id": None, "status": "error", "message": "Bad request"}
    assert server.handle_line('{"id":"q","op":"dance"}') == {"id": "q", "status": "error", "message": "Bad request"}


def test_correction_is_saved_under_user_dir_and_loads_back(server, tmp_path):
    from inkmath_reader import corrections
    r = server.handle({"id": "c1", "op": "correction", "ink": [_ink_b64()], "recognized": "3x-1=11", "corrected": "3x-7=11"})
    assert r == {"id": "c1", "status": "saved"}
    files = list((tmp_path / "corrections").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["recognized"] == "3x-1=11" and data["corrected"] == "3x-7=11"
    [(strokes, latex)] = corrections.load(tmp_path / "corrections")
    assert latex == "3x-7=11" and len(strokes) == 2


def test_tuned_weights_used_only_when_accepted(tmp_path):
    from inkmath_reader.server import choose_weights
    assert choose_weights(tmp_path) is None
    tuned = tmp_path / "texteller-tuned"
    tuned.mkdir()
    (tuned / "accepted.json").write_text(json.dumps({"accepted": False}), encoding="utf-8")
    assert choose_weights(tmp_path) is None
    (tuned / "accepted.json").write_text(json.dumps({"accepted": True}), encoding="utf-8")
    assert choose_weights(tmp_path) == tuned


def test_calibration_default_and_file(tmp_path):
    from inkmath_reader.calibration import low_threshold
    assert low_threshold(tmp_path) == 0.85
    (tmp_path / "reader_calibration.json").write_text(json.dumps({"low_threshold": 0.7}), encoding="utf-8")
    assert low_threshold(tmp_path) == 0.7


@pytest.mark.model
@pytest.mark.skipif(not (REPO / "models" / "huggingface").exists(), reason="no TexTeller weights")
def test_process_round_trip(tmp_path):
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), PYTHONUTF8="1")
    p = subprocess.Popen([sys.executable, "-m", "inkmath_reader", "--models", str(REPO / "models")], cwd=READER,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         encoding="utf-8", env=env)
    try:
        ready = json.loads(p.stdout.readline())
        assert ready["status"] == "ready" and ready["model"] in ("texteller", "texteller-tuned") and ready["load_ms"] > 0
        p.stdin.write(json.dumps({"id": "r1", "op": "read", "ink": [_ink_b64()]}) + "\n")
        p.stdin.flush()
        reply = json.loads(p.stdout.readline())
        assert reply["id"] == "r1" and reply["status"] in ("ok", "empty")
        p.stdin.close()
        t0 = time.time()
        p.wait(timeout=5)
        assert time.time() - t0 < 5
    finally:
        if p.poll() is None:
            p.kill()

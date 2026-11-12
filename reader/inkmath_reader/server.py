"""JSON-lines reader service: one warm TexTeller, one request per line on stdin, one reply per line on stdout.

Startup prints {"status":"ready",...} once the model is loaded. The process exits when stdin closes.
Logs go to stderr only.
"""
import argparse
import base64
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from . import corrections, paths
from .calibration import low_threshold
from .ink import NoInk, decode_items
from .render import render
from .symbols import build_symbols

NO_INK = "Lasso some handwriting first."
EMPTY = "Couldn't read any math in this ink."
FAILED = "Couldn't read this handwriting."
BAD_REQUEST = "Bad request"
TUNED_DIR = "texteller-tuned"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def choose_weights(models_dir: Path) -> Path | None:
    """The tuned weights, but only when the tuning gate accepted them."""
    tuned = Path(models_dir) / TUNED_DIR
    flag = tuned / "accepted.json"
    if flag.exists() and json.loads(flag.read_text(encoding="utf-8")).get("accepted") is True:
        return tuned
    return None


def _ms(t0: float) -> int:
    return int(round((time.perf_counter() - t0) * 1000))


class Server:
    def __init__(self, recognizer, user_dir: Path, low_threshold: float):
        self.rec, self.user_dir, self.low = recognizer, Path(user_dir), low_threshold

    def handle_line(self, line: str) -> dict:
        try:
            msg = json.loads(line)
        except ValueError:
            return {"id": None, "status": "error", "message": BAD_REQUEST}
        if not isinstance(msg, dict):
            return {"id": None, "status": "error", "message": BAD_REQUEST}
        return self.handle(msg)

    def handle(self, msg: dict) -> dict:
        rid, op = msg.get("id"), msg.get("op")
        try:
            if op == "read":
                return self._read(rid, msg.get("ink"))
            if op == "correction":
                strokes = self._strokes(msg.get("ink"))
                corrections.save(self.user_dir / "corrections", strokes, str(msg.get("recognized", "")),
                                 str(msg.get("corrected", "")))
                return {"id": rid, "status": "saved"}
        except NoInk:
            return {"id": rid, "status": "no_ink", "message": NO_INK}
        except Exception as e:  # never die on one bad request
            _log(f"{op} {rid} failed: {type(e).__name__}: {e}")
            return {"id": rid, "status": "error", "message": FAILED}
        return {"id": rid, "status": "error", "message": BAD_REQUEST}

    @staticmethod
    def _strokes(ink) -> list:
        if not ink or not isinstance(ink, list):
            raise NoInk("no ink items")
        strokes = decode_items([base64.b64decode(item) for item in ink])
        if not any(strokes):
            raise NoInk("no ink points")
        return strokes

    def _read(self, rid, ink) -> dict:
        t0 = time.perf_counter()
        img = render(self._strokes(ink))
        t_ink = _ms(t0)
        t1 = time.perf_counter()
        reading = self.rec.read(img)
        t_model = _ms(t1)
        if not reading.latex.strip():
            return {"id": rid, "status": "empty", "message": EMPTY}
        snippet = self.user_dir / "selections" / "last.png"
        snippet.parent.mkdir(parents=True, exist_ok=True)
        img.save(snippet)
        symbols = [asdict(s) for s in build_symbols(reading, self.low)]
        return {"id": rid, "status": "ok", "latex": reading.latex, "symbols": symbols, "snippet": str(snippet),
                "model": self.rec.name, "ms": {"ink": t_ink, "model": t_model, "total": _ms(t0)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inkmath_reader")
    ap.add_argument("--models", help="model files directory (default: <repo>/models or INKMATH_MODELS)")
    ap.add_argument("--file", help="read one saved selection (M3 last.json), print the reply and exit")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdin.reconfigure(encoding="utf-8")

    from .recognize import Recognizer
    models = paths.models_dir(args.models)
    t0 = time.perf_counter()
    rec = Recognizer(models, choose_weights(models))
    server = Server(rec, paths.user_dir(), low_threshold(models))
    load_ms = _ms(t0)
    _log(f"reader loaded {rec.name} in {load_ms} ms")

    if args.file:
        saved = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
        reply = server.handle({"id": "file", "op": "read", "ink": [i["isf"] for i in saved.get("ink", [])]})
        print(json.dumps(reply, ensure_ascii=False), flush=True)
        return 0 if reply["status"] in ("ok", "empty") else 1

    print(json.dumps({"status": "ready", "model": rec.name, "load_ms": load_ms}), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        print(json.dumps(server.handle_line(line), ensure_ascii=False), flush=True)
    return 0

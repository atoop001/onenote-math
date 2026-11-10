"""Subprocess tests of the JSON-lines protocol M3 uses: python -m inkmath_solver [--checkin N]."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from subprocess import PIPE, Popen

import pytest

SOLVER = Path(__file__).resolve().parents[1]
SLOW = {"id": "slow", "latex": r"\int e^{x^2}\sin(x^3)\cos(\sqrt{x})dx", "operation": "integrate"}
_procs = []


def start(*args):
    p = Popen([sys.executable, "-m", "inkmath_solver", *args], stdin=PIPE, stdout=PIPE, stderr=PIPE,
              text=True, encoding="utf-8", cwd=SOLVER)
    _procs.append(p)
    assert json.loads(p.stdout.readline()) == {"ready": True}
    return p


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    while _procs:
        p = _procs.pop()
        try:
            p.stdin.close()
            p.wait(15)
        except Exception:
            p.kill()


def send(p, obj):
    p.stdin.write(json.dumps(obj) + "\n")
    p.stdin.flush()


def read(p):
    return json.loads(p.stdout.readline())


def ask(p, obj):
    send(p, obj)
    return read(p)


def kill_worker_child(p):
    while True:
        m = re.search(r"worker pid (\d+)", p.stderr.readline())
        if m:
            subprocess.run(["taskkill", "/F", "/PID", m.group(1)], capture_output=True)
            return


def test_roundtrip():
    p = start()
    r = ask(p, {"id": "a", "latex": "3x-7=11"})
    assert r["id"] == "a" and r["answer"]["text"] == "x = 6"
    p.stdin.close()
    assert p.wait(10) == 0


def test_checkin_asks_and_keeps_working():
    p = start("--checkin", "1")
    send(p, SLOW)
    r = read(p)
    assert r["status"] == "still_working" and r["message"] == "This one's taking a while. Keep going or stop?"
    send(p, {"id": "slow", "control": "continue"})
    assert read(p)["status"] == "still_working"   # asked again after another second: still computing


def test_stop_then_recovers():
    p = start("--checkin", "1")
    send(p, SLOW)
    assert read(p)["status"] == "still_working"
    t = time.monotonic()
    send(p, {"id": "slow", "control": "stop"})
    r = read(p)
    assert r["status"] == "stopped" and r["message"] == "Stopped." and time.monotonic() - t < 2
    assert ask(p, {"id": "b", "latex": "3x-7=11"})["status"] == "ok"


def test_stop_before_checkin():
    p = start("--checkin", "20")
    send(p, SLOW)
    send(p, {"id": "slow", "control": "stop"})
    assert read(p)["status"] == "stopped"


def test_request_queued_during_solve():
    p = start("--checkin", "1")
    send(p, SLOW)
    send(p, {"id": "q", "latex": "x+1=2"})
    assert read(p)["status"] == "still_working"
    send(p, {"id": "slow", "control": "stop"})
    assert read(p)["status"] == "stopped"
    r = read(p)
    assert r["id"] == "q" and r["status"] == "ok"


def test_stale_control_ignored():
    p = start()
    send(p, {"id": "nope", "control": "stop"})
    assert ask(p, {"id": "f", "latex": "x+1=2"})["id"] == "f"


def test_bad_json_keeps_serving():
    p = start()
    p.stdin.write("not json\n")
    p.stdin.flush()
    assert read(p)["status"] == "error"
    assert ask(p, {"id": "c", "latex": "x+1=2"})["status"] == "ok"


def test_unknown_operation_is_error_with_id():
    p = start()
    r = ask(p, {"id": "u", "latex": "x", "operation": "graph"})
    assert r["status"] == "error" and r["id"] == "u"


def test_worker_crash_recovers():
    p = start()
    kill_worker_child(p)
    assert ask(p, {"id": "d", "latex": "x+1=2"})["status"] in ("ok", "error")
    assert ask(p, {"id": "e", "latex": "x+1=2"})["status"] == "ok"

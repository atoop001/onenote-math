"""Test stand-in for `python -m inkmath_reader`: python stub_reader.py <ok|slowready|silent|crash> [marker].

silent and crash misbehave only on the first read ever (until the marker file exists), so a restarted
stub answers normally.
"""
import json
import os
import sys
import time

mode = sys.argv[1]
marker = sys.argv[2] if len(sys.argv) > 2 else None
sys.stdout.reconfigure(encoding="utf-8", newline="\n")
if mode == "slowready":
    time.sleep(600)
print('{"status": "ready", "model": "texteller", "load_ms": 1234}', flush=True)


def first_time():
    if marker is None or os.path.exists(marker):
        return False
    open(marker, "w").close()
    return True


for line in sys.stdin:
    req = json.loads(line)
    if mode == "crash" and first_time():
        sys.exit(3)
    if mode == "silent" and first_time():
        continue
    symbols = [{"text": c, "start": i, "end": i + 1, "confidence": 0.5 if c == "7" else 0.99, "low": c == "7",
                "alternatives": ["1", "\\tau"] if c == "7" else []} for i, c in enumerate("3x-7=11")]
    print(json.dumps({"id": req["id"], "status": "ok", "latex": "3x-7=11", "symbols": symbols,
                      "snippet": "C:\\snip\\last.png", "model": "texteller",
                      "ms": {"ink": 40, "model": 1300, "total": 1400}, "inkCount": len(req.get("ink", []))}),
          flush=True)

"""Test stand-in for `python -m inkmath_solver`: python stub_solver.py <answer|stderr|silent|crash|noready>."""
import json
import sys
import time

mode = sys.argv[1]
sys.stdout.reconfigure(encoding="utf-8", newline="\n")
if mode == "noready":
    time.sleep(600)
print('{"ready": true}', flush=True)
for line in sys.stdin:
    req = json.loads(line)
    if "control" in req:
        continue
    if mode == "crash":
        sys.exit(3)
    if mode == "silent":
        continue
    if mode == "stderr":
        for _ in range(1024):
            sys.stderr.write("x" * 1023 + "\n")
        sys.stderr.flush()
    print(json.dumps({"id": req["id"], "status": "ok", "answer": {"latex": "x=6", "text": "x = 6", "decimal": None},
                      "verified": True, "source": "Solved offline · verified"}, ensure_ascii=False), flush=True)

"""Latency bench: every prompt through one warm server, the way the add-in will call it.

    python -m inkmath_solver.bench --set ../samples/prompts_test.json

Prints id, status, verified, wall ms per prompt (answering needs_operation with choices[0]), then the median,
the max and how many took over 5 s. Surface estimate = dev time × 1.75 (M1 measurement).
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

SURFACE_FACTOR = 1.75


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inkmath_solver.bench")
    ap.add_argument("--set", required=True, help="prompts JSON file")
    args = ap.parse_args(argv)
    prompts = json.load(open(args.set, encoding="utf-8"))
    p = subprocess.Popen([sys.executable, "-m", "inkmath_solver"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, encoding="utf-8", cwd=Path(__file__).resolve().parents[1])
    assert json.loads(p.stdout.readline()) == {"ready": True}

    def ask(obj):
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()
        while True:
            r = json.loads(p.stdout.readline())
            if r["status"] != "still_working":
                return r

    times, bad = [], 0
    for q in prompts:
        t0 = time.perf_counter()
        r = ask({"id": q["id"], "latex": q["latex"]})
        if r["status"] == "needs_operation":
            t0 = time.perf_counter()            # the tutor's menu tap starts a new clock
            r = ask({"id": q["id"], "latex": q["latex"], "operation": r["choices"][0]})
        ms = (time.perf_counter() - t0) * 1000
        times.append(ms)
        bad += r["status"] in ("error", "stopped")
        print(f"{q['id']}  {r['status']:<15} {'verified' if r['verified'] else '-':<9} {ms:7.0f} ms")
    p.stdin.close()
    p.wait(15)
    med, mx = statistics.median(times), max(times)
    print(f"\nmedian {med:.0f} ms, max {mx:.0f} ms, over 5 s: {sum(t > 5000 for t in times)}, errors: {bad}")
    print(f"Surface estimate (×{SURFACE_FACTOR}): median {med * SURFACE_FACTOR:.0f} ms, max {mx * SURFACE_FACTOR:.0f} ms")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

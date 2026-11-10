"""JSON-lines solver process (the protocol M3's C# add-in uses).

stdin:  one JSON object per line — a request ({"id", "latex", ...}) or a control ({"id", "control": "continue"|"stop"}).
stdout: one JSON object per line — for each request zero or more "still_working" check-ins, then exactly one
        final response. Nothing else is written to stdout; logs go to stderr.

The server never imports SymPy. A warm worker process does the math, so a slow solve can always be stopped
(spec §3: every --checkin seconds ask "Keep going or stop?"; never stop work on its own).
"""
import argparse
import json
import multiprocessing as mp
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import asdict

from .schema import CONTROLS, Response, request_from_dict, response_to_json

CHECKIN_MESSAGE = "This one's taking a while. Keep going or stop?"
STOPPED_MESSAGE = "Stopped."
CRASH_MESSAGE = "Something went wrong solving this"
_EOF = object()


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------- worker (child process) ----------

def _watch_parent() -> None:
    parent = mp.parent_process()
    while parent is not None and parent.is_alive():
        time.sleep(1)
    import os
    os._exit(0)          # the server is gone: don't keep computing as an orphan


def worker_main(conn) -> None:
    threading.Thread(target=_watch_parent, daemon=True).start()
    from .engine import handle
    from .parse import parse_problem
    parse_problem("x+1")                       # warm the LaTeX parser
    conn.send("ready")
    while True:
        try:
            d = conn.recv()
        except (EOFError, OSError):
            return
        conn.send(asdict(handle(request_from_dict(d))))


class Worker:
    def __init__(self):
        self.ctx = mp.get_context("spawn")
        self.proc = None
        self.conn = None
        self.ready = False

    def start(self) -> None:
        parent, child = self.ctx.Pipe()
        self.proc = self.ctx.Process(target=worker_main, args=(child,), daemon=True)
        self.proc.start()
        child.close()
        self.conn, self.ready = parent, False
        _log(f"worker pid {self.proc.pid}")

    def wait_ready(self) -> bool:
        if self.ready:
            return True
        try:
            self.ready = self.conn.recv() == "ready"
        except (EOFError, OSError):
            self.ready = False
        return self.ready

    def alive(self) -> bool:
        return self.proc is not None and self.proc.is_alive()

    def kill(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            self.proc.join(5)
        if self.conn is not None:
            self.conn.close()

    def restart(self) -> None:
        self.kill()
        self.start()


# ---------- server (parent process) ----------

def _private_stdin():
    """Our own handle to stdin; children get NUL instead.

    On Windows a new process that inherits a pipe while another thread has a pending read on it blocks at
    startup until a line arrives. Workers are (re)started while the reader thread waits, so they must never
    inherit the real stdin.
    """
    import os
    fd = os.dup(0)                      # non-inheritable copy (PEP 446)
    nul = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nul, 0)                     # also resets STD_INPUT_HANDLE, which children inherit
    os.close(nul)
    return open(fd, encoding="utf-8")


class Server:
    def __init__(self, checkin: float, stdin=None):
        self.stdin = stdin if stdin is not None else sys.stdin
        self.checkin = checkin
        self.lines: queue.Queue = queue.Queue()
        self.pending: deque = deque()
        self.worker = Worker()
        self.eof = False

    def write(self, obj) -> None:
        line = obj if isinstance(obj, str) else response_to_json(obj)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def _reader(self) -> None:
        for line in self.stdin:
            if line.strip():
                self.lines.put(line)
        self.lines.put(_EOF)

    def _decode(self, line):
        """(kind, payload): ('control', dict) | ('request', Request) | ('error', Response)."""
        try:
            d = json.loads(line)
        except ValueError:
            return "error", Response(id="", status="error", message="Couldn't read that request")
        rid = d.get("id", "") if isinstance(d, dict) else ""
        if isinstance(d, dict) and "control" in d:
            if d["control"] in CONTROLS:
                return "control", d
            return "error", Response(id=str(rid), status="error", message="Unknown control")
        try:
            return "request", request_from_dict(d)
        except (ValueError, TypeError):
            return "error", Response(id=str(rid) if isinstance(rid, str) else "", status="error",
                                     message="Couldn't read that request")

    def _ensure_worker(self) -> None:
        if not self.worker.alive():
            self.worker.restart()
        if not self.worker.wait_ready():
            self.worker.restart()
            self.worker.wait_ready()

    def _run(self, req) -> None:
        self._ensure_worker()
        try:
            self.worker.conn.send(asdict(req))
        except (OSError, EOFError):
            self.worker.restart()
            self.write(Response(id=req.id, status="error", message=CRASH_MESSAGE))
            return
        last = time.monotonic()
        while True:
            try:
                if self.worker.conn.poll(0.1):
                    self.write(Response(**_with_answer(self.worker.conn.recv())))
                    return
            except (EOFError, OSError):
                self.worker.restart()
                self.write(Response(id=req.id, status="error", message=CRASH_MESSAGE))
                return
            if not self.worker.alive():
                self.worker.restart()
                self.write(Response(id=req.id, status="error", message=CRASH_MESSAGE))
                return
            while True:                                  # handle lines that arrived meanwhile
                try:
                    line = self.lines.get_nowait()
                except queue.Empty:
                    break
                if line is _EOF:
                    self.eof = True
                    self.worker.kill()
                    return
                kind, payload = self._decode(line)
                if kind == "control" and payload["id"] == req.id:
                    if payload["control"] == "continue":
                        last = time.monotonic()
                    else:
                        self.worker.restart()
                        self.write(Response(id=req.id, status="stopped", message=STOPPED_MESSAGE))
                        return
                elif kind == "control":
                    _log(f"ignored {payload['control']} for {payload['id']!r}: not running")
                elif kind == "request":
                    self.pending.append(payload)
                else:
                    self.write(payload)
            if time.monotonic() - last >= self.checkin:
                self.write(Response(id=req.id, status="still_working", message=CHECKIN_MESSAGE))
                last = time.monotonic()

    def serve(self) -> int:
        threading.Thread(target=self._reader, daemon=True).start()
        self.worker.start()
        self.worker.wait_ready()
        self.write('{"ready": true}')
        while not self.eof:
            if self.pending:
                self._run(self.pending.popleft())
                continue
            line = self.lines.get()
            if line is _EOF:
                break
            kind, payload = self._decode(line)
            if kind == "request":
                self._run(payload)
            elif kind == "control":
                _log(f"ignored {payload['control']} for {payload['id']!r}: not running")
            else:
                self.write(payload)
        self.worker.kill()
        return 0


def _with_answer(d: dict) -> dict:
    from .schema import Answer
    if d.get("answer"):
        d["answer"] = Answer(**d["answer"])
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inkmath_solver")
    ap.add_argument("--checkin", type=float, default=20.0, help="seconds between 'keep going or stop?' check-ins")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    return Server(args.checkin, _private_stdin()).serve()

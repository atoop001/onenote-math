"""Request/response types shared by the engine, the server, and (via JSON) the C# add-in."""
import json
from dataclasses import asdict, dataclass, field, fields

OPERATIONS = ("simplify", "factor", "expand", "solve", "solve_system", "evaluate", "evaluate_at",
              "derivative", "implicit_derivative", "integrate", "limit", "series", "identity", "ode")
STATUSES = ("ok", "needs_operation", "cannot_parse", "cannot_solve", "still_working", "stopped", "error")
CONTROLS = ("continue", "stop")  # control lines: {"id": "<request id>", "control": "continue" | "stop"}

SOURCE_VERIFIED = "Solved offline · verified"
SOURCE_UNVERIFIED = "Solved offline · ⚠ unverified"


@dataclass
class Request:
    id: str
    latex: str
    operation: str | None = None
    variable: str | None = None
    point: str | None = None
    show_steps: bool = True


@dataclass
class Answer:
    latex: str
    text: str
    decimal: str | None


@dataclass
class Response:
    id: str
    status: str
    operation: str | None = None
    variable: str | None = None
    choices: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    answer: Answer | None = None
    notes: list[str] = field(default_factory=list)
    verified: bool = False
    source: str = ""
    message: str = ""
    ms: int = 0


def request_from_dict(d: dict) -> Request:
    if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not isinstance(d.get("latex"), str):
        raise ValueError("request needs string 'id' and 'latex'")
    names = {f.name for f in fields(Request)}
    req = Request(**{k: v for k, v in d.items() if k in names})
    if req.operation is not None and req.operation not in OPERATIONS:
        raise ValueError(f"unknown operation: {req.operation}")
    return req


def request_from_json(line: str) -> Request:
    return request_from_dict(json.loads(line))


def response_to_json(r: Response) -> str:
    return json.dumps(asdict(r), ensure_ascii=False)

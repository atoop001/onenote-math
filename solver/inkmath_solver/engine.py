"""Request → Response: parse, pick or ask the operation, run it, verify it. Never raises."""
import logging
import time

from sympy import Symbol

from .infer import infer_operation
from .ops.algebra import (run_evaluate, run_evaluate_at, run_expand, run_factor, run_identity, run_simplify,
                          run_solve, run_solve_system)
from .ops.base import CannotSolve
from .ops.calculus import run_derivative, run_implicit_derivative, run_integrate, run_limit, run_ode
from .ops.series import run_series
from .parse import ParseError, parse_problem
from .schema import SOURCE_UNVERIFIED, SOURCE_VERIFIED, Request, Response
from .verify import verify

log = logging.getLogger(__name__)

RUNNERS = {
    "simplify": run_simplify, "factor": run_factor, "expand": run_expand, "solve": run_solve,
    "solve_system": run_solve_system, "evaluate": run_evaluate, "evaluate_at": run_evaluate_at,
    "derivative": run_derivative, "implicit_derivative": run_implicit_derivative, "integrate": run_integrate,
    "limit": run_limit, "series": run_series, "identity": run_identity, "ode": run_ode,
}
ERROR_MESSAGE = "Something went wrong solving this"


def _pick_variable(p, name):
    if name:
        for s in p.symbols:
            if s.name == name:
                return s
        return Symbol(name)
    return p.symbols[0] if p.symbols else None


def _handle(req: Request, t0: float) -> Response:
    try:
        p = parse_problem(req.latex)
    except ParseError as e:
        return Response(id=req.id, status="cannot_parse", message=e.message)
    op = req.operation
    choices = []
    if op is None:
        op, choices = infer_operation(p)
        if op is None:
            return Response(id=req.id, status="needs_operation", choices=choices,
                            message="What should I do with this?")
    var = _pick_variable(p, req.variable)
    point = None
    if op == "evaluate_at":
        if not req.point:
            return Response(id=req.id, status="cannot_solve", operation=op, message="Which value should I use?")
        try:
            point = parse_problem(req.point).expr
        except ParseError:
            return Response(id=req.id, status="cannot_parse", operation=op, message="Couldn't read that value")
    try:
        result = RUNNERS[op](p, var, point)
    except CannotSolve as e:
        return Response(id=req.id, status="cannot_solve", operation=op, variable=var and var.name,
                        message=e.message)
    verified = result.checkable and verify(op, p, result, var)
    return Response(
        id=req.id, status="ok", operation=op, variable=var.name if var is not None else None,
        choices=choices, steps=list(result.steps) if req.show_steps else [], answer=result.answer,
        notes=list(result.notes), verified=verified, source=SOURCE_VERIFIED if verified else SOURCE_UNVERIFIED)


def handle(req: Request) -> Response:
    t0 = time.perf_counter()
    try:
        r = _handle(req, t0)
    except Exception:
        log.exception("solver error on %r", req.latex)
        r = Response(id=req.id, status="error", message=ERROR_MESSAGE)
    r.ms = int((time.perf_counter() - t0) * 1000)
    return r

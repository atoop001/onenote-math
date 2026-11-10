import json

import pytest

from inkmath_solver.schema import Answer, Response, request_from_json, response_to_json


def test_request_roundtrip_defaults():
    r = request_from_json('{"id":"1","latex":"x+1=2"}')
    assert r.operation is None and r.show_steps is True


def test_response_json_is_one_line_unicode():
    s = response_to_json(Response(id="1", status="ok", answer=Answer("\\pi", "π", "3.14159")))
    assert "\n" not in s and "π" in s and json.loads(s)["answer"]["decimal"] == "3.14159"


def test_unknown_operation_rejected():
    with pytest.raises(ValueError):
        request_from_json('{"id":"1","latex":"x","operation":"graph"}')

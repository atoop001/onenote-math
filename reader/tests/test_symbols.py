"""Symbol units, confidence mapping and alternatives (hand-built readings, no model)."""
from inkmath_reader.recognize import RawReading, TokenStep
from inkmath_reader.symbols import CONFUSIONS, build_symbols, split_symbols


def reading(latex, steps):
    return RawReading(latex, "".join(t for t, _, _ in steps), [TokenStep(t, p, a) for t, p, a in steps])


def test_split_handles_commands_escapes_and_spaces():
    s = r"\frac{3}{x} \leq 2"
    units = split_symbols(s)
    assert [t for t, _, _ in units] == ["\\frac", "{", "3", "}", "{", "x", "}", "\\leq", "2"]
    assert all(s[a:b] == t for t, a, b in units)
    assert [t for t, _, _ in split_symbols(r"\{x\}")] == ["\\{", "x", "\\}"]


def test_confidence_is_min_over_overlapping_tokens():
    syms = build_symbols(reading(r"\frac", [("\\fr", 0.9, []), ("ac", 0.6, [])]), 0.85)
    assert [(s.text, s.confidence) for s in syms] == [("\\frac", 0.6)]


def test_formatting_changes_keep_confidences():
    r = reading("x ^{2}", [("x", 0.99, []), ("^{", 0.95, []), ("2", 0.7, []), ("}", 0.98, [])])
    syms = build_symbols(r, 0.85)
    assert [s.text for s in syms] == ["x", "^", "{", "2", "}"]
    assert [s.confidence for s in syms] == [0.99, 0.95, 0.95, 0.7, 0.98]
    assert all(r.latex[s.start:s.end] == s.text for s in syms)


def test_replaced_block_takes_block_minimum():
    r = reading("c+1", [("a", 0.9, []), ("b", 0.5, []), ("+", 0.99, []), ("1", 0.97, [])])
    syms = build_symbols(r, 0.85)
    assert [(s.text, s.confidence) for s in syms] == [("c", 0.5), ("+", 0.99), ("1", 0.97)]


def test_inserted_formatting_is_certain():
    r = reading("{x}", [("x", 0.8, [])])
    assert [(s.text, s.confidence) for s in build_symbols(r, 0.85)] == [("{", 1.0), ("x", 0.8), ("}", 1.0)]


def test_alternatives_come_from_model_then_confusions():
    r = reading("5", [("5", 0.4, [("6", 0.1), ("S", 0.05)])])
    assert build_symbols(r, 0.85)[0].alternatives == ["6", "S", "s"]


def test_multi_unit_alternatives_are_dropped():
    r = reading("5", [("5", 0.4, [("5x", 0.2), (" 6", 0.1), ("5", 0.05)])])
    assert build_symbols(r, 0.85)[0].alternatives == ["6", "s"]


def test_syntax_pieces_are_not_offered_for_a_symbol():
    r = reading("x", [("x", 0.5, [("\\", 0.2), ("_", 0.1), ("{", 0.05), ("X", 0.04)])])
    assert build_symbols(r, 0.85)[0].alternatives == ["X", "\\times"]


def test_syntax_pieces_may_replace_each_other():
    r = reading("x^2", [("x", 0.99, []), ("^", 0.5, [("_", 0.3)]), ("2", 0.99, [])])
    assert build_symbols(r, 0.85)[1].alternatives == ["_"]


def test_alternatives_rebuild_inside_a_command():
    r = reading(r"\leq", [("\\le", 0.5, [("\\ge", 0.3)]), ("q", 0.99, [])])
    assert build_symbols(r, 0.85)[0].alternatives[0] == "\\geq"


def test_low_flag_uses_threshold():
    r = reading("xy", [("x", 0.84, []), ("y", 0.85, [])])
    assert [s.low for s in build_symbols(r, 0.85)] == [True, False]


def test_confusions_are_symmetric():
    for a, alts in CONFUSIONS.items():
        for b in alts:
            assert a in CONFUSIONS[b], (a, b)
    assert "\\times" in CONFUSIONS["x"] and "s" in CONFUSIONS["5"]

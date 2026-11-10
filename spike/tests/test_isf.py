from inkspike.isf import decode_isf, encode_isf


def test_isf_roundtrip():
    s = [[(0, 0), (10, 5), (20, 0)], [(5, 10), (5, 30)]]
    out = decode_isf(encode_isf(s))
    assert len(out) == 2 and len(out[0]) >= 3


def test_decode_keeps_position():
    out = decode_isf(encode_isf([[(100, 200), (110, 210)]]))
    x, y = out[0][0]
    assert abs(x - 100) < 2 and abs(y - 200) < 2

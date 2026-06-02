from app.workers.strategy import _weighted_rr


def test_weighted_rr_long_balanced():
    rr = _weighted_rr(entry=100.0, stop=99.0, take_profit=[102.0])
    assert abs(rr - 2.0) < 1e-9


def test_weighted_rr_long_two_targets():
    rr = _weighted_rr(entry=100.0, stop=99.0, take_profit=[102.0, 103.0])
    assert abs(rr - 2.5) < 1e-9


def test_weighted_rr_returns_zero_for_no_risk():
    assert _weighted_rr(entry=100.0, stop=100.0, take_profit=[101.0]) == 0.0


def test_weighted_rr_returns_zero_for_empty_targets():
    assert _weighted_rr(entry=100.0, stop=99.0, take_profit=[]) == 0.0

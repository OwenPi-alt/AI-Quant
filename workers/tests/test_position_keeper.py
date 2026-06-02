from app.workers.position_keeper import _evaluate, _parse_tp


def test_evaluate_long_hits_stop():
    out = _evaluate("LONG", mid=99.0, entry=100.0, stop=99.5, take_profit=[105.0])
    assert out == (99.5, "STOP_LOSS")


def test_evaluate_long_hits_target():
    out = _evaluate("LONG", mid=106.0, entry=100.0, stop=99.5, take_profit=[105.0, 110.0])
    assert out == (105.0, "TAKE_PROFIT")


def test_evaluate_long_open_no_trigger():
    assert _evaluate("LONG", mid=101.0, entry=100.0, stop=99.5, take_profit=[105.0]) is None


def test_evaluate_short_hits_stop():
    out = _evaluate("SHORT", mid=101.0, entry=100.0, stop=100.5, take_profit=[95.0])
    assert out == (100.5, "STOP_LOSS")


def test_evaluate_short_hits_target():
    out = _evaluate("SHORT", mid=94.0, entry=100.0, stop=100.5, take_profit=[95.0])
    assert out == (95.0, "TAKE_PROFIT")


def test_parse_tp_handles_list_of_numbers():
    assert _parse_tp([1.0, 2.0]) == [1.0, 2.0]


def test_parse_tp_handles_dict_entries():
    assert _parse_tp([{"px": 1.5}, {"price": 2.5}]) == [1.5, 2.5]


def test_parse_tp_handles_json_string():
    assert _parse_tp("[1.0, 2.0]") == [1.0, 2.0]


def test_parse_tp_handles_none():
    assert _parse_tp(None) == []

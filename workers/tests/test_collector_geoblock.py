from app.workers.collector import _is_blocked


def test_is_blocked_true_bool():
    assert _is_blocked({"blocked": True}) is True


def test_is_blocked_true_string():
    assert _is_blocked({"isBlocked": "true"}) is True


def test_is_blocked_false_when_missing():
    assert _is_blocked({}) is False


def test_is_blocked_none():
    assert _is_blocked(None) is False


def test_is_blocked_false_when_false_bool():
    assert _is_blocked({"blocked": False}) is False

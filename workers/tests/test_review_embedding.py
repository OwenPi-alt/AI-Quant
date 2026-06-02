from app.workers.review import EMBEDDING_DIM, _deterministic_embedding


def test_embedding_dim():
    out = _deterministic_embedding("hello-world")
    assert len(out) == EMBEDDING_DIM


def test_embedding_determinism():
    a = _deterministic_embedding("BTCUSDT|LONG|67000|66500")
    b = _deterministic_embedding("BTCUSDT|LONG|67000|66500")
    assert a == b


def test_embedding_differs_for_different_input():
    a = _deterministic_embedding("BTCUSDT|LONG")
    b = _deterministic_embedding("BTCUSDT|SHORT")
    assert a != b


def test_embedding_unit_norm():
    out = _deterministic_embedding("xyz")
    norm_sq = sum(v * v for v in out)
    assert abs(norm_sq - 1.0) < 1e-6

import asyncio

from app.services.embedding import (
    DEFAULT_EMBEDDING_DIM,
    DeterministicEmbedder,
    OpenAICompatEmbedder,
    make_embedder,
)
from app.settings import Settings
from app.workers.review import _deterministic_embedding


def test_deterministic_matches_legacy_helper():
    text = "BTCUSDT|LONG|67000|66500"
    embedder = DeterministicEmbedder(dim=DEFAULT_EMBEDDING_DIM)
    new = asyncio.run(embedder.embed(text))
    legacy = _deterministic_embedding(text)
    assert new == legacy


def test_deterministic_is_unit_norm():
    embedder = DeterministicEmbedder()
    out = asyncio.run(embedder.embed("hello"))
    norm_sq = sum(v * v for v in out)
    assert abs(norm_sq - 1.0) < 1e-6


def test_make_embedder_default_is_deterministic():
    settings = Settings(embedding_provider="", api_auth_token="x")
    embedder = make_embedder(settings)
    assert isinstance(embedder, DeterministicEmbedder)


def test_make_embedder_falls_back_when_api_key_missing():
    settings = Settings(embedding_provider="openai_compat", embedding_api_key="")
    embedder = make_embedder(settings)
    assert isinstance(embedder, DeterministicEmbedder)


def test_make_embedder_returns_compat_when_configured():
    settings = Settings(embedding_provider="openai_compat", embedding_api_key="sk-test")
    embedder = make_embedder(settings)
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert embedder.model == settings.embedding_model
    assert embedder.dim == DEFAULT_EMBEDDING_DIM


def test_openai_compat_falls_back_on_network_error():
    embedder = OpenAICompatEmbedder(
        base_url="http://127.0.0.1:1",  # nothing listening
        api_key="sk-bad",
        model="any",
        dim=DEFAULT_EMBEDDING_DIM,
        timeout=0.05,
    )
    out = asyncio.run(embedder.embed("anything"))
    assert len(out) == DEFAULT_EMBEDDING_DIM
    # falls back to deterministic, which is byte-identical to the legacy helper
    assert out == _deterministic_embedding("anything")

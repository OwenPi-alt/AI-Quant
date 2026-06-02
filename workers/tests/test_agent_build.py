from app.workers.agent import build_agent_json, build_query_text


class _Row(dict):
    """asyncpg.Record-like dict used in tests; supports row['key'] access."""


def _signal():
    return {
        "id": "sig-1",
        "symbol": "BTCUSDT",
        "market": "BINANCE_FUTURES_PAPER",
        "direction": "LONG",
        "strategy": "trend_following_v1",
        "confidence": 0.67,
        "entry_min": 67000.0,
        "entry_max": 67500.0,
        "stop_loss": 66500.0,
        "take_profit": [68500.0, 69000.0],
        "risk_reward_ratio": 2.0,
        "features": {"ma20": 67100.0, "funding": 0.0001},
    }


def _wiki(idx: int, title: str, sim: float):
    return _Row(
        id=f"wiki-{idx}",
        category="funding",
        title=title,
        body=title + " body",
        tags=["funding", "test"],
        confidence=0.7,
        weight=1.0,
        similarity=sim,
        symbol=None,
        market=None,
        needs_embedding=False,
    )


def _experience(idx: int, summary: str, sim: float):
    return _Row(
        id=f"exp-{idx}",
        symbol="BTCUSDT",
        market="BINANCE_FUTURES_PAPER",
        summary=summary,
        outcome={"hit_tp": True},
        error_tags=[],
        similarity=sim,
    )


def test_build_agent_json_includes_wiki_and_experience_hints():
    wikis = [_wiki(1, "Funding spike", 0.81), _wiki(2, "Stop too tight", 0.62)]
    experiences = [_experience(1, "BTC long trend", 0.78)]
    agent_json = build_agent_json(_signal(), experiences, wikis)
    assert agent_json["symbol"] == "BTCUSDT"
    assert agent_json["direction"] == "LONG"
    assert len(agent_json["wiki_hints"]) == 2
    assert agent_json["wiki_hints"][0]["title"] == "Funding spike"
    assert agent_json["wiki_hints"][0]["similarity"] == 0.81
    assert len(agent_json["experience_hints"]) == 1
    assert agent_json["experience_hints"][0]["id"] == "exp-1"
    assert "wiki: Funding spike" in agent_json["reasoning_summary"]
    for field in (
        "entry",
        "stop_loss",
        "take_profit",
        "risk_reward_ratio",
        "confidence",
        "max_position_size",
        "invalidation_condition",
        "reasoning_summary",
        "related_memories",
        "news_sources",
        "sentiment_score",
        "risk_flags",
    ):
        assert field in agent_json


def test_build_agent_json_no_wiki_no_experience():
    agent_json = build_agent_json(_signal(), [], [])
    assert agent_json["wiki_hints"] == []
    assert agent_json["experience_hints"] == []
    assert agent_json["related_memories"] == []
    assert "wiki:" not in agent_json["reasoning_summary"]


def test_build_query_text_contains_market_symbol_direction():
    text = build_query_text(_signal())
    assert "BTCUSDT" in text
    assert "BINANCE_FUTURES_PAPER" in text
    assert "LONG" in text
    assert "trend_following_v1" in text

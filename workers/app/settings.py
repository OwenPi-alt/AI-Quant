from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Trim whitespace from any secret-bearing field. .env values copied
    # from a terminal or a password manager often include trailing newlines
    # or spaces, which would otherwise silently 401 every API call.
    @field_validator(
        "api_auth_token",
        "embedding_api_key",
        "telegram_bot_token",
        "telegram_chat_id",
        "llm_api_key",
        "hermes_webhook_secret",
        mode="before",
    )
    @classmethod
    def _strip_secret(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    worker_role: str = "collector"
    database_url: str = "postgresql://ai_quant:ai_quant@localhost:5432/ai_quant"
    control_api_url: str = "http://localhost:8080"
    api_auth_token: str = ""

    binance_spot_base_url: str = "https://api.binance.com"
    binance_futures_base_url: str = "https://fapi.binance.com"
    binance_symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"

    hyperliquid_info_url: str = "https://api.hyperliquid-testnet.xyz/info"
    hyperliquid_coins: str = "BTC,ETH,SOL"

    polymarket_mode: str = "OBSERVE_ONLY"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_geoblock_url: str = "https://polymarket.com/api/geoblock"

    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""

    # Embedding provider for wiki + experience recall.
    # provider: "deterministic" (default, zero-cost SHA-256) or "openai_compat".
    embedding_provider: str = "deterministic"
    embedding_base_url: str = "https://api.deepseek.com"
    embedding_model: str = "deepseek-embedding"
    embedding_api_key: str = ""
    embedding_dim: int = 1536

    # How many wiki entries / past experiences to inject into each agent_json.
    recall_wiki_limit: int = 5
    recall_experience_limit: int = 5

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    hermes_webhook_url: str = ""
    hermes_webhook_secret: str = ""

    account_equity_usd: float = 1000.0
    min_agent_confidence: float = 0.65
    min_risk_reward: float = 1.5
    max_entry_deviation_pct: float = 0.003

    @property
    def symbols(self) -> list[str]:
        return [item.strip().upper() for item in self.binance_symbols.split(",") if item.strip()]

    @property
    def hyperliquid_coin_list(self) -> list[str]:
        return [item.strip().upper() for item in self.hyperliquid_coins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

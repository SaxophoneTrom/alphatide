"""Application settings loaded from environment variables (.env).

Tunables for the detector live here too, so thresholds can be changed without
touching code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Secrets / endpoints ---
    telegram_bot_token: str = ""
    surf_api_key: str = ""
    mantle_rpc_url: str = "https://rpc.mantle.xyz"
    mantle_chain_id: int = 5000
    mantlescan_api_key: str = ""

    # --- Detector tunables ---
    # Minimum USD value of a transfer/swap to treat the actor as a candidate.
    min_candidate_usd: float = 10_000.0
    # How many recent blocks to scan per cycle (Mantle ~2s/block).
    scan_block_window: int = 1_500
    # Surf labels are cached this long (seconds). Identity is near-constant.
    label_cache_ttl: int = 7 * 24 * 3600
    # Entity types we consider "smart money" worth alerting on.
    smart_entity_types: tuple[str, ...] = (
        "fund",
        "cex",
        "market_maker",
        "market-maker",
        "smart_money",
        "smart-money",
        "whale",
        "vc",
        "trader",
    )
    # Run a detection cycle every N seconds in monitor mode.
    monitor_interval: int = 180


settings = Settings()

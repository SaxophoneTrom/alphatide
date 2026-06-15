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

    # Volume anomaly: only flag spikes whose absolute window volume clears this
    # floor (avoids alerting on tiny-number outliers). Drops are never alerted.
    anomaly_min_volume_usd: float = 50_000.0
    # And require the spike to be at least this many times the baseline — a 3σ
    # move that's only 1.7× normal is statistically odd but economically nothing.
    anomaly_min_ratio: float = 3.0
    # Push gate: an anomaly is only *pushed* to subscribers if this dramatic.
    # Below this it's still logged (visible via /recent) but doesn't ping anyone.
    anomaly_push_ratio: float = 5.0

    # --- Abuse protection (public bot) ---
    # Max expensive commands a single user may trigger per 60s.
    rate_limit_per_min: int = 6
    # Global ceiling on Surf credits spent per UTC day (users + monitor share it).
    daily_credit_budget: int = 500
    # Where the push-subscriber list is persisted (survives restarts).
    subscribers_file: str = ".state/subscribers.json"
    # Append-only history of pushed alerts (auditable; survives restarts).
    alerts_file: str = ".state/alerts.jsonl"
    # Comma-separated Telegram chat IDs allowed to run /demo. Empty = anyone
    # (still rate-limited + budget-gated).
    owner_chat_ids: str = ""

    @property
    def owners(self) -> set[int]:
        out: set[int] = set()
        for part in self.owner_chat_ids.split(","):
            part = part.strip()
            if part:
                try:
                    out.add(int(part))
                except ValueError:
                    pass
        return out


settings = Settings()

"""Application settings loaded from environment variables (.env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str = ""
    surf_api_key: str = ""
    mantle_rpc_url: str = "https://rpc.mantle.xyz"
    mantle_chain_id: int = 5000
    mantlescan_api_key: str = ""


settings = Settings()

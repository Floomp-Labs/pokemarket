from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    poll_interval_seconds: int = 900
    alert_pct_threshold: float = 4.0
    alert_z_threshold: float = 1.75
    alert_cooldown_minutes: int = 60
    grade_alert_pct_threshold: float = 6.0
    stale_snapshot_hours: int = 6
    pokemontcg_api_key: Optional[str] = None
    database_url: str = "sqlite:///./pokemon.db"
    # Comma-separated extra browser origins allowed to call the API
    # (e.g. your Vercel domain). localhost:5173 is always allowed.
    cors_origins: str = ""


settings = Settings()

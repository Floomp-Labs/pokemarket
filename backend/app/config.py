from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    poll_interval_seconds: int = 900
    alert_pct_threshold: float = 4.0
    alert_z_threshold: float = 1.75
    alert_cooldown_minutes: int = 60
    grade_alert_pct_threshold: float = 6.0
    # Cross-source price disagreement (%) that counts as an anomaly, and how
    # long before the same subject can raise another spread alert.
    alert_spread_pct_threshold: float = 5.0
    spread_cooldown_minutes: int = 720
    # US-vs-EU gap (%, Cardmarket FX-adjusted) that counts as exceptional.
    regional_spread_pct_threshold: float = 25.0
    eur_usd_rate: float = 1.08
    stale_snapshot_hours: int = 6
    pokemontcg_api_key: Optional[str] = None
    database_url: str = "sqlite:///./pokemon.db"
    # Comma-separated extra browser origins allowed to call the API
    # (e.g. your Vercel domain). localhost:5173 is always allowed.
    cors_origins: str = ""
    # Bearer token protecting POST /api/collect (Vercel cron / GitHub
    # Actions). Unset = endpoint is open (fine for local dev only).
    collect_token: Optional[str] = None


settings = Settings()

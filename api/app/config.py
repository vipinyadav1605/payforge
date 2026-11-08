from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://payforge:payforge@db:5432/payforge"
    redis_url: str = "redis://redis:6379/0"
    admin_token: str = "dev-admin-token-change-me"

    platform_fee_bps: int = 250  # 2.50% platform fee, in basis points

    rate_limit_enabled: bool = True
    rate_limit_capacity: int = 20  # bucket size (burst)
    rate_limit_refill_per_sec: float = 10.0  # sustained requests per second

    db_pool_size: int = 10
    db_max_overflow: int = 10

    webhook_timeout_seconds: float = 5.0
    webhook_max_attempts: int = 6
    outbox_batch_size: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    ope_env: str = 'local'
    ope_service_name: str = 'ope-core'
    ope_default_project: str = 'ope-core'
    ope_skip_external_init: bool = False
    ope_disable_event_logging: bool = False

    litellm_base_url: str = 'http://litellm:4000'
    litellm_model: str = 'deep_reasoning'
    litellm_api_key: str | None = None

    postgres_dsn: str = 'postgresql://ope:ope-local-dev@postgres:5432/ope'
    redis_url: str = 'redis://redis:6379/0'

    request_timeout_seconds: int = 120
    provider_cooldown_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()

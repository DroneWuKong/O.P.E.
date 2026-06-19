from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    ope_env: str = 'local'
    ope_service_name: str = 'ope-core'
    ope_default_project: str = 'ope-core'
    ope_skip_external_init: bool = False
    ope_disable_event_logging: bool = False
    ope_require_api_key: bool = False
    ope_api_keys: str = ''
    ope_run_migrations_on_startup: bool = True
    ope_startup_retry_seconds: int = 120
    ope_startup_retry_interval_seconds: float = 5.0
    ope_external_connect_timeout_seconds: float = 5.0

    litellm_base_url: str = 'http://litellm:4000'
    litellm_model: str = 'deep_reasoning'
    litellm_api_key: str | None = None

    postgres_dsn: str = 'postgresql://ope:ope-local-dev@postgres:5432/ope'
    redis_url: str = 'redis://redis:6379/0'

    request_timeout_seconds: int = 120
    provider_cooldown_seconds: int = 60

    tool_runner_worker_id: str = 'ope-tool-runner'
    tool_runner_project: str | None = None
    tool_runner_poll_seconds: float = 5.0
    tool_runner_lease_seconds: int = 300
    tool_runner_once: bool = False

    github_token: str | None = None
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_api_base_url: str = 'https://api.github.com'

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_access_token: str | None = None
    google_service_account_json: str | None = None
    google_drive_enabled: bool = True
    gmail_enabled: bool = False
    gmail_access_token: str | None = None
    google_api_base_url: str = 'https://www.googleapis.com'

    ope_upload_root: str = '/tmp/ope-uploads'
    ope_upload_max_bytes: int = 25 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

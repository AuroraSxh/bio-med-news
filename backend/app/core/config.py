from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(
        default="postgresql+psycopg://biomed:biomed_password@postgres:5432/biomed_news",
        alias="DATABASE_URL",
    )
    admin_refresh_token: str = Field(default="change_me", alias="ADMIN_REFRESH_TOKEN")
    glm5_base_url: str = Field(default="", alias="GLM5_BASE_URL")
    glm5_api_key: str = Field(default="change_me", alias="GLM5_API_KEY")
    glm5_model_name: str = Field(default="glm-5", alias="GLM5_MODEL_NAME")
    ingestion_timezone: str = Field(default="Asia/Shanghai", alias="INGESTION_TIMEZONE")
    ingestion_schedule_hours: str = Field(default="8,12,18", alias="INGESTION_SCHEDULE_HOURS")
    ingestion_max_items_per_source: int = Field(default=12, alias="INGESTION_MAX_ITEMS_PER_SOURCE", ge=1, le=50)
    ingestion_sources_json: str = Field(default="", alias="INGESTION_SOURCES_JSON")
    worker_run_on_startup: bool = Field(default=True, alias="WORKER_RUN_ON_STARTUP")
    source_config_path: str = Field(default="config/sources.json", alias="SOURCE_CONFIG_PATH")
    source_request_timeout_seconds: float = Field(default=15.0, alias="SOURCE_REQUEST_TIMEOUT_SECONDS")
    source_request_max_attempts: int = Field(default=3, alias="SOURCE_REQUEST_MAX_ATTEMPTS", ge=1, le=5)
    source_request_backoff_seconds: float = Field(default=1.5, alias="SOURCE_REQUEST_BACKOFF_SECONDS", ge=0, le=30)
    glm5_request_timeout_seconds: float = Field(default=120.0, alias="GLM5_REQUEST_TIMEOUT_SECONDS")
    llm_stream_chunk_timeout_seconds: float = Field(default=30.0, alias="LLM_STREAM_CHUNK_TIMEOUT_SECONDS")
    glm5_request_max_attempts: int = Field(default=3, alias="GLM5_REQUEST_MAX_ATTEMPTS", ge=1, le=5)
    glm5_request_backoff_seconds: float = Field(default=2.0, alias="GLM5_REQUEST_BACKOFF_SECONDS", ge=0, le=60)
    seed_sample_data: bool = Field(default=False, alias="SEED_SAMPLE_DATA")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["text", "json"] = Field(default="text", alias="LOG_FORMAT")


@lru_cache
def get_settings() -> Settings:
    return Settings()

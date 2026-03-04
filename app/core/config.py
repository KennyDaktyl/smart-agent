from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ===== BASE PATH =====
    BASE_DIR: Path = Path.cwd()

    # ===== ENVIRONMENT =====
    ENV: str = Field("development", env="ENV")

    # ===== LOGGING =====
    LOG_DIR: str = Field("logs", env="LOG_DIR")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # ===== CONFIG FILE =====
    CONFIG_FILE: str = Field("config.json", env="CONFIG_FILE")

    # ===== AUTH =====
    BACKEND_URL: str | None = Field(None, env="BACKEND_URL")
    BACKEND_AGENT_TOKEN: str | None = Field(None, env="BACKEND_AGENT_TOKEN")
    SENTRY_DSN: str | None = Field(None, env="SENTRY_DSN")

    # ===== NATS =====
    NATS_URL: str = Field(..., env="NATS_URL")
    NATS_PREFIX: str = Field("device_communication", env="NATS_PREFIX")

    # ===== AGENT SELF UPDATE =====
    AGENT_SELF_UPDATE_CWD: str = Field("/app", env="AGENT_SELF_UPDATE_CWD")
    AGENT_SELF_UPDATE_SERVICE: str = Field("agent", env="AGENT_SELF_UPDATE_SERVICE")
    AGENT_SELF_UPDATE_COMPOSE_FILE: str | None = Field(
        None,
        env="AGENT_SELF_UPDATE_COMPOSE_FILE",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

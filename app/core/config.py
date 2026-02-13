from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ===== BASE PATH =====
    BASE_DIR: Path = Path.cwd()

    # ===== LOGGING =====
    LOG_DIR: str = Field("logs", env="LOG_DIR")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # ===== CONFIG FILE =====
    CONFIG_FILE: str = Field("config.json", env="CONFIG_FILE")

    # ===== AUTH =====
    BACKEND_URL: str | None = Field(None, env="BACKEND_URL")
    BACKEND_AGENT_TOKEN: str | None = Field(None, env="BACKEND_AGENT_TOKEN")

    # ===== NATS =====
    NATS_URL: str = Field(..., env="NATS_URL")
    NATS_PREFIX: str = Field("device_communication", env="NATS_PREFIX")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

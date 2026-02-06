# app/core/config.py
import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    NATS_URL: str = Field("nats://localhost:4222", env="NATS_URL")
    HEARTBEAT_INTERVAL: int = Field(30, env="HEARTBEAT_INTERVAL")

    LOG_DIR: str = Field("logs", env="LOG_DIR")
    CONFIG_FILE: str = Field("config.json", env="CONFIG_FILE")
    BACKEND_URL: str | None = Field(None, env="BACKEND_URL")
    RASPBERRY_UUID: str = Field(env="RASPBERRY_UUID")

    BACKEND_AGENT_TOKEN: str | None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def load_gpio_config() -> dict:
    config_file = Path(settings.CONFIG_FILE)
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                data = json.load(f)
                return data.get("gpio_pins", {})
        except json.JSONDecodeError:
            print("Failed to decode JSON from config file.")
    return {}

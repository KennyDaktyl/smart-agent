import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    RASPBERRY_UUID: str = Field(..., description="Unique ID Raspberry Pi")
    SECRET_KEY: str = Field(..., description="Secret key for secure operations")

    NATS_URL: str = Field("nats://localhost:4222", env="NATS_URL")
    HEARTBEAT_INTERVAL: int = Field(30, env="HEARTBEAT_INTERVAL")

    GPIO_PINS: dict = Field(default_factory=dict)
    LOG_DIR: str = Field("logs", env="LOG_DIR")
    CONFIG_FILE: str = Field("config", env="CONFIG_FILE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


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


settings.GPIO_PINS = load_gpio_config()

from pathlib import Path

from app.core.config import settings
from app.core.logging_config import logging

CONFIG_FILE = Path(settings.CONFIG_FILE)

logging.info(f"Config path: {CONFIG_FILE}")

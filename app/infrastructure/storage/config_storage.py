from pathlib import Path

from app.core.config import settings
from app.core.logging_config import logger

CONFIG_FILE = Path(settings.CONFIG_FILE)

logger.info(f"Config path: {CONFIG_FILE}")

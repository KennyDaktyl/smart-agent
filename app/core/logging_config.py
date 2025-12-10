# app/core/logging_config.py
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings

# Resolve log path relative to the project root to avoid surprises with CWD.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
log_dir = Path(settings.LOG_DIR)
if not log_dir.is_absolute():
    log_dir = PROJECT_ROOT / log_dir
log_dir.mkdir(parents=True, exist_ok=True)
LOG_FILE_PATH = log_dir / "logs.log"

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s]  %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

# Handlers: console + rotating file.
file_handler = TimedRotatingFileHandler(
    LOG_FILE_PATH,
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8",
    delay=True,  # create file lazily to avoid issues during import
)
file_handler.suffix = "%Y-%m-%d"
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

for handler in list(root_logger.handlers):
    root_logger.removeHandler(handler)

root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

for name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
    log = logging.getLogger(name)
    log.handlers = root_logger.handlers
    log.setLevel(logging.INFO)
    log.propagate = False

# Export a named logger for convenience imports (e.g., `from app.core.logging_config import logger`).
# It writes to both console and the rotating log file.
logger = logging.getLogger("smart_energy_agent")
logger.setLevel(logging.INFO)
logger.handlers = []
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False

root_logger.info(f"✅ Logging initialized. Writing logs to: {LOG_FILE_PATH}")
root_logger.info(f"logging start time UTC: {datetime.now(timezone.utc).isoformat()}")

__all__ = ["logging", "logger"]

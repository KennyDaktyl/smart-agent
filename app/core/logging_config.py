import logging
import sys
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings


# ===== PATH SETUP =====

base_log_dir = Path(settings.LOG_DIR)

if not base_log_dir.is_absolute():
    base_log_dir = settings.BASE_DIR / base_log_dir

base_log_dir.mkdir(parents=True, exist_ok=True)

log_file_path = base_log_dir / "agent.log"


# ===== FORMAT =====

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)


# ===== FILE HANDLER (daily rotation) =====

file_handler = TimedRotatingFileHandler(
    filename=log_file_path,
    when="midnight",
    interval=1,
    backupCount=14,
    encoding="utf-8",
    utc=True,
    delay=True,
)

file_handler.suffix = "%Y-%m-%d.log"
file_handler.setFormatter(formatter)


# ===== CONSOLE =====

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)


# ===== ROOT LOGGER =====

log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(log_level)

# clear existing handlers
for handler in list(root_logger.handlers):
    root_logger.removeHandler(handler)

file_handler.setLevel(log_level)
console_handler.setLevel(log_level)

root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)


# ===== APP LOGGER =====

logger = logging.getLogger("smart_energy_agent")
logger.setLevel(log_level)
logger.propagate = True


root_logger.info("✅ Logging initialized")
root_logger.info(f"📂 Base dir: {settings.BASE_DIR}")
root_logger.info(f"📂 Logs dir: {base_log_dir}")
root_logger.info(f"🕒 Start time UTC: {datetime.now(timezone.utc).isoformat()}")


__all__ = ["logging", "logger"]

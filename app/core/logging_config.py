# app/core/logging_config.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from .config import settings

LOG_DIR = settings.LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOG_DIR, "logs.log")

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

file_handler = RotatingFileHandler(
    LOG_FILE_PATH, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

for handler in list(root_logger.handlers):
    root_logger.removeHandler(handler)

root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

for name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
    log = logging.getLogger(name)
    log.handlers = root_logger.handlers
    log.setLevel(logging.INFO)
    log.propagate = True

logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
logger.propagate = True

logger.info(f"Logging initialized. Writing logs to: {LOG_FILE_PATH}")

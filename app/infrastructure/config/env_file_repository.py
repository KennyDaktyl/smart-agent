import errno
import os
from pathlib import Path

from app.core.config import settings
from app.core.logging_config import logger


class EnvFileRepository:
    def __init__(self):
        self._env_path = self._resolve_path()

    def _resolve_path(self) -> Path:
        return settings.BASE_DIR / ".env"

    def read(self) -> str:
        if not self._env_path.exists():
            return ""
        return self._env_path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        if not isinstance(content, str):
            raise ValueError("env_file_content must be a string")

        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._env_path.with_suffix(".tmp")

        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            tmp_path.replace(self._env_path)
            logger.info("Env file saved (atomic write)")
            return
        except OSError as exc:
            if exc.errno not in {errno.EBUSY, errno.EXDEV, errno.EPERM}:
                raise

            logger.warning(
                "Atomic replace failed for env file (%s). Falling back to in-place write: %s",
                self._env_path,
                exc,
            )

        with self._env_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            logger.debug("Failed to remove temp env file: %s", tmp_path)

        logger.info("Env file saved (in-place write)")


env_file_repository = EnvFileRepository()

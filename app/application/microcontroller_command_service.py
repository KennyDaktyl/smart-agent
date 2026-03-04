import asyncio
import logging
import os
import subprocess
from typing import Any

from app.core.config import settings
from app.domain.events.enums import MicrocontrollerCommandType
from app.infrastructure.config.domain_config_repository import domain_config_repository
from app.infrastructure.config.env_file_repository import env_file_repository
from app.infrastructure.config.hardware_config_repository import (
    hardware_config_repository,
)

logger = logging.getLogger(__name__)


class MicrocontrollerCommandService:
    async def handle_command(
        self,
        *,
        command: MicrocontrollerCommandType,
        config_json: dict[str, Any] | None = None,
        hardware_config_json: dict[str, Any] | None = None,
        env_file_content: str | None = None,
    ) -> dict[str, Any]:
        try:
            if command == MicrocontrollerCommandType.READ_CONFIG_FILES:
                return {
                    "ok": True,
                    "config_json": domain_config_repository.export_json(),
                    "hardware_config_json": hardware_config_repository.export_json(),
                    "env_file_content": env_file_repository.read(),
                }

            if command == MicrocontrollerCommandType.WRITE_CONFIG_FILES:
                if not isinstance(config_json, dict) or not isinstance(
                    hardware_config_json,
                    dict,
                ) or not isinstance(
                    env_file_content,
                    str,
                ):
                    return {
                        "ok": False,
                        "message": (
                            "config_json, hardware_config_json and env_file_content "
                            "are required "
                            "for WRITE_CONFIG_FILES command"
                        ),
                    }

                domain_config_repository.replace_from_json(config_json)
                hardware_config_repository.replace_from_json(hardware_config_json)
                env_file_repository.write(env_file_content)
                return {
                    "ok": True,
                    "message": "Configuration files saved",
                }

            if command == MicrocontrollerCommandType.REBOOT_AGENT:
                return {
                    "ok": True,
                    "message": "Agent reboot scheduled",
                    "reboot_scheduled": True,
                }

            if command == MicrocontrollerCommandType.UPDATE_AGENT:
                return {
                    "ok": True,
                    "message": "Agent update scheduled",
                    "update_scheduled": True,
                }

            return {
                "ok": False,
                "message": f"Unsupported microcontroller command: {command}",
            }
        except Exception as exc:
            logger.exception("Failed to execute microcontroller command: %s", command)
            return {
                "ok": False,
                "message": str(exc) or "Failed to execute microcontroller command",
            }

    async def reboot_after_ack(self, delay_seconds: float = 0.3) -> None:
        await asyncio.sleep(delay_seconds)
        logger.warning("Rebooting agent process")
        os._exit(0)

    async def update_after_ack(self, delay_seconds: float = 0.3) -> None:
        await asyncio.sleep(delay_seconds)

        compose_cmd = ["docker", "compose"]
        compose_file = (settings.AGENT_SELF_UPDATE_COMPOSE_FILE or "").strip()
        if compose_file:
            compose_cmd.extend(["-f", compose_file])

        service = settings.AGENT_SELF_UPDATE_SERVICE.strip() or "agent"
        cwd = settings.AGENT_SELF_UPDATE_CWD

        pull_cmd = [*compose_cmd, "pull", service]
        up_cmd = [*compose_cmd, "up", "-d", service]

        logger.warning(
            "Running agent self-update | cwd=%s pull_cmd=%s up_cmd=%s",
            cwd,
            " ".join(pull_cmd),
            " ".join(up_cmd),
        )

        try:
            await asyncio.to_thread(self._run_command, pull_cmd, cwd)
            await asyncio.to_thread(self._run_command, up_cmd, cwd)
        except Exception:
            logger.exception("Agent self-update failed")

    def _run_command(self, command: list[str], cwd: str) -> None:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

        if result.stdout:
            logger.info(
                "Command stdout | command=%s\n%s",
                " ".join(command),
                result.stdout.strip(),
            )
        if result.stderr:
            logger.warning(
                "Command stderr | command=%s\n%s",
                " ".join(command),
                result.stderr.strip(),
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed ({result.returncode}): {' '.join(command)}"
            )


microcontroller_command_service = MicrocontrollerCommandService()

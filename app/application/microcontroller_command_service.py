import asyncio
import logging
import os
import shutil
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
                validation_error = self._validate_update_prerequisites()
                if validation_error:
                    return {
                        "ok": False,
                        "message": validation_error,
                    }
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

        compose_cmd, _ = self._build_compose_command()
        if not compose_cmd:
            logger.error(
                "Agent self-update skipped: docker/docker-compose binary not found"
            )
            return

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

    def _validate_update_prerequisites(self) -> str | None:
        compose_cmd, compose_file = self._build_compose_command()
        if not compose_cmd:
            return (
                "Missing docker CLI in agent container. Install docker/docker-compose "
                "or mount docker binary."
            )

        cwd = settings.AGENT_SELF_UPDATE_CWD
        if not os.path.isdir(cwd):
            return f"AGENT_SELF_UPDATE_CWD does not exist: {cwd}"

        if compose_file and not os.path.isfile(compose_file):
            return (
                "AGENT_SELF_UPDATE_COMPOSE_FILE does not exist: "
                f"{compose_file}"
            )
        if not compose_file and not self._has_default_compose_file(cwd):
            return (
                "No compose file found in AGENT_SELF_UPDATE_CWD. "
                "Expected one of: compose.yml, compose.yaml, "
                "docker-compose.yml, docker-compose.yaml"
            )

        return None

    def _build_compose_command(self) -> tuple[list[str] | None, str | None]:
        compose_file = (settings.AGENT_SELF_UPDATE_COMPOSE_FILE or "").strip() or None

        docker_bin = shutil.which("docker")
        if docker_bin:
            command = [docker_bin, "compose"]
            if compose_file:
                command.extend(["-f", compose_file])
            return command, compose_file

        docker_compose_bin = shutil.which("docker-compose")
        if docker_compose_bin:
            command = [docker_compose_bin]
            if compose_file:
                command.extend(["-f", compose_file])
            return command, compose_file

        return None, compose_file

    def _run_command(self, command: list[str], cwd: str) -> None:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Command not found: {command[0]}") from exc

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

    def _has_default_compose_file(self, cwd: str) -> bool:
        candidates = (
            "compose.yml",
            "compose.yaml",
            "docker-compose.yml",
            "docker-compose.yaml",
        )
        return any(
            os.path.isfile(os.path.join(cwd, file_name)) for file_name in candidates
        )


microcontroller_command_service = MicrocontrollerCommandService()

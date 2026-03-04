import asyncio
import logging
import os
from typing import Any

from app.domain.events.enums import MicrocontrollerCommandType
from app.infrastructure.config.domain_config_repository import domain_config_repository
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
    ) -> dict[str, Any]:
        try:
            if command == MicrocontrollerCommandType.READ_CONFIG_FILES:
                return {
                    "ok": True,
                    "config_json": domain_config_repository.export_json(),
                    "hardware_config_json": hardware_config_repository.export_json(),
                }

            if command == MicrocontrollerCommandType.WRITE_CONFIG_FILES:
                if not isinstance(config_json, dict) or not isinstance(
                    hardware_config_json,
                    dict,
                ):
                    return {
                        "ok": False,
                        "message": (
                            "Both config_json and hardware_config_json are required "
                            "for WRITE_CONFIG_FILES command"
                        ),
                    }

                domain_config_repository.replace_from_json(config_json)
                hardware_config_repository.replace_from_json(hardware_config_json)
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


microcontroller_command_service = MicrocontrollerCommandService()

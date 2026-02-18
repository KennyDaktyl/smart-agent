import logging

from app.application.device_factory import merge_configs
from app.domain.events.device_events import (
    DeviceCommandPayload,
    DeviceCreatedPayload,
    DeviceDeletePayload,
    DeviceUpdatedPayload,
)
from app.domain.models.agent_config import DeviceConfig, DeviceMode
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
    backend_adapter,
)
from app.infrastructure.config.domain_config_repository import (
    domain_config_repository,
)
from app.infrastructure.config.hardware_config_repository import (
    hardware_config_repository,
)
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)


class GPIOService:

    @staticmethod
    def _to_mode(mode: str | DeviceMode) -> DeviceMode:
        if isinstance(mode, DeviceMode):
            return mode
        return DeviceMode(mode)

    @staticmethod
    def _mode_value(mode: object) -> str:
        return mode.value if hasattr(mode, "value") else str(mode)

    @staticmethod
    def _find_device_number_by_id(device_id: int) -> int | None:
        domain_config = domain_config_repository.load()
        for device_number, device in domain_config.devices.items():
            if device.device_id == device_id:
                return device_number
        return None

    @staticmethod
    def _persist_candidate_config(candidate_config) -> bool:
        hardware_config = hardware_config_repository.load()
        merged_devices = merge_configs(candidate_config, hardware_config)
        domain_config_repository.update(**candidate_config.model_dump())
        gpio_manager.load_devices(merged_devices)
        return True

    def create_device(self, payload: DeviceCreatedPayload) -> bool:
        domain_config = domain_config_repository.load()
        device_number = int(payload.device_number)

        if device_number in domain_config.devices:
            logger.error(
                "Cannot create device: device_number=%s already exists",
                device_number,
            )
            return False

        try:
            mode = self._to_mode(payload.mode)
        except ValueError:
            logger.error("Invalid device mode for create: %s", payload.mode)
            return False

        candidate_config = domain_config.model_copy(deep=True)
        candidate_config.devices[device_number] = DeviceConfig(
            device_id=payload.device_id,
            mode=mode,
            power_threshold=payload.threshold_kw,
        )

        try:
            self._persist_candidate_config(candidate_config)
        except Exception:
            logger.exception("Failed to create device %s", payload.device_id)
            return False

        logger.info(
            "Device created: number=%s id=%s mode=%s",
            device_number,
            payload.device_id,
            mode.value,
        )
        return True

    def update_device(self, payload: DeviceUpdatedPayload) -> bool:
        domain_config = domain_config_repository.load()
        device_number = self._find_device_number_by_id(payload.device_id)

        if device_number is None:
            logger.error(
                "Cannot update device: device_id=%s not found",
                payload.device_id,
            )
            return False

        try:
            mode = self._to_mode(payload.mode)
        except ValueError:
            logger.error("Invalid device mode for update: %s", payload.mode)
            return False

        candidate_config = domain_config.model_copy(deep=True)
        candidate_device = candidate_config.devices[device_number]
        candidate_device.mode = mode
        candidate_device.power_threshold = payload.threshold_kw

        try:
            self._persist_candidate_config(candidate_config)
        except Exception:
            logger.exception("Failed to update device %s", payload.device_id)
            return False

        logger.info(
            "Device updated: number=%s id=%s mode=%s threshold=%s",
            device_number,
            payload.device_id,
            mode.value,
            payload.threshold_kw,
        )
        return True

    def delete_device(self, payload: DeviceDeletePayload) -> bool:
        domain_config = domain_config_repository.load()
        device_number = self._find_device_number_by_id(payload.device_id)

        if device_number is None:
            logger.error(
                "Cannot delete device: device_id=%s not found",
                payload.device_id,
            )
            return False

        candidate_config = domain_config.model_copy(deep=True)
        candidate_config.devices.pop(device_number, None)

        try:
            self._persist_candidate_config(candidate_config)
        except Exception:
            logger.exception("Failed to delete device %s", payload.device_id)
            return False

        logger.info(
            "Device deleted: number=%s id=%s",
            device_number,
            payload.device_id,
        )
        return True

    def set_manual_state(self, payload: DeviceCommandPayload) -> bool:
        device = gpio_manager.get_by_id(payload.device_id)
        if not device:
            logger.error("Cannot set manual state: device_id=%s not found", payload.device_id)
            return False

        if self._mode_value(device.mode) != DeviceMode.MANUAL.value:
            logger.info(
                "Ignoring manual command for device_id=%s in mode=%s",
                payload.device_id,
                self._mode_value(device.mode),
            )
            return False

        changed = gpio_manager.set_state_by_number(
            device.device_number,
            payload.is_on,
        )
        if not changed:
            return False

        backend_adapter.log_device_event(
            device_id=device.device_id,
            event_type=DeviceEventType.STATE,
            pin_state=payload.is_on,
            trigger_reason="DEVICE_COMMAND",
        )
        return True


gpio_service = GPIOService()

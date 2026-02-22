import logging
import asyncio
from typing import Optional

from app.application.device_factory import merge_configs
from app.core.device_event_stream_service import device_event_stream_service
from app.core.heartbeat_service import (
    HeartbeatPublishTrigger,
    heartbeat_service,
)
from app.domain.events.device_events import (
    DeviceCommandPayload,
    DeviceCreatedPayload,
    DeviceDeletePayload,
    DeviceUpdatedPayload,
)
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import AgentConfig, DeviceConfig, DeviceMode
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
    DeviceTriggerReason,
    backend_adapter,
)
from app.infrastructure.config.domain_config_repository import domain_config_repository
from app.infrastructure.config.hardware_config_repository import (
    hardware_config_repository,
)
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)


class GPIOService:

    @staticmethod
    def _collect_runtime_states() -> dict[int, bool]:
        return {
            device_number: gpio_manager.read_is_on_by_number(device_number)
            for device_number in gpio_manager.devices_by_number.keys()
        }

    @staticmethod
    def _emit_backend_state_change_event(
        *,
        device_uuid: str | None,
        device_id: int | None,
        device_number: int,
        is_on: bool,
        trigger_reason: DeviceTriggerReason,
    ) -> None:
        backend_adapter.log_device_event(
            device_uuid=device_uuid,
            device_id=device_id,
            device_number=device_number,
            event_type=DeviceEventType.STATE,
            is_on=is_on,
            trigger_reason=trigger_reason,
        )

    @staticmethod
    def _publish_state_change_device_event_async(
        *,
        device: RuntimeDevice,
        is_on: bool,
        event_type: DeviceEventType,
        trigger_reason: DeviceTriggerReason,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        loop.create_task(
            device_event_stream_service.publish_state_change(
                device=device,
                is_on=is_on,
                event_type=event_type,
                trigger_reason=trigger_reason,
            )
        )

    @staticmethod
    def _publish_heartbeat_after_state_change_async(
        *,
        device_number: int,
        trigger_reason: DeviceTriggerReason,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _publish() -> None:
            published = await heartbeat_service.publish_now(
                trigger=HeartbeatPublishTrigger.STATE_CHANGE,
            )
            if not published:
                logger.warning(
                    "Immediate heartbeat publish failed after state change "
                    "| device_number=%s trigger_reason=%s",
                    device_number,
                    trigger_reason.value,
                )

        loop.create_task(_publish())

    def _emit_state_changes_after_reload(
        self,
        *,
        previous_states: dict[int, bool],
    ) -> None:
        for device_number, device in gpio_manager.devices_by_number.items():
            current_state = gpio_manager.read_is_on_by_number(device_number)
            previous_state = previous_states.get(device_number)

            if previous_state is None:
                if not current_state:
                    continue
            elif previous_state == current_state:
                continue

            self._emit_backend_state_change_event(
                device_uuid=device.device_uuid,
                device_id=device.device_id,
                device_number=device_number,
                is_on=current_state,
                trigger_reason=DeviceTriggerReason.CONFIG_APPLY,
            )
            self._publish_state_change_device_event_async(
                device=device,
                is_on=current_state,
                event_type=DeviceEventType.STATE,
                trigger_reason=DeviceTriggerReason.CONFIG_APPLY,
            )
            self._publish_heartbeat_after_state_change_async(
                device_number=device_number,
                trigger_reason=DeviceTriggerReason.CONFIG_APPLY,
            )

    @staticmethod
    def _to_mode(mode: str | DeviceMode) -> DeviceMode:
        if isinstance(mode, DeviceMode):
            return mode
        return DeviceMode(mode)

    def _persist_candidate_config(self, candidate_config: AgentConfig) -> bool:
        previous_states = self._collect_runtime_states()
        hardware_config = hardware_config_repository.load()
        merged_devices = merge_configs(candidate_config, hardware_config)
        domain_config_repository.update(**candidate_config.model_dump())
        gpio_manager.load_devices(merged_devices)
        self._emit_state_changes_after_reload(previous_states=previous_states)
        return True

    def sync_device_state_to_config(
        self,
        *,
        device_number: int,
        mode_override: Optional[DeviceMode] = None,
    ) -> bool:
        try:
            domain_config = domain_config_repository.load()
            if device_number not in domain_config.devices:
                logger.error(
                    "Cannot sync state: device_number=%s not found in config",
                    device_number,
                )
                return False

            actual_state = gpio_manager.read_is_on_by_number(device_number)
            candidate_config = domain_config.model_copy(deep=True)
            candidate_device = candidate_config.devices[device_number]

            if mode_override is not None:
                candidate_device.mode = mode_override

            if candidate_device.mode == DeviceMode.MANUAL:
                candidate_device.desired_state = actual_state
            else:
                candidate_device.desired_state = None

            domain_config_repository.update(**candidate_config.model_dump())

            runtime_device = gpio_manager.get_by_number(device_number)
            if runtime_device:
                runtime_device.mode = candidate_device.mode
                runtime_device.desired_state = candidate_device.desired_state

            return True
        except Exception:
            logger.exception("Failed to sync state for device_number=%s", device_number)
            return False

    @staticmethod
    def _is_valid_device_number(device_number: int, device_max: int) -> bool:
        return 1 <= device_number <= device_max

    def create_device(self, payload: DeviceCreatedPayload) -> bool:
        domain_config = domain_config_repository.load()
        device_number = int(payload.device_number)

        if not self._is_valid_device_number(device_number, domain_config.device_max):
            logger.error(
                "Cannot create device: device_number=%s outside valid range 1..%s",
                device_number,
                domain_config.device_max,
            )
            return False

        if len(domain_config.devices) >= domain_config.device_max:
            logger.error(
                "Cannot create device: device_max reached (%s)",
                domain_config.device_max,
            )
            return False

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

        requested_is_on = bool(payload.is_on)
        initial_desired_state = None
        if mode == DeviceMode.MANUAL:
            initial_desired_state = requested_is_on

        candidate_config = domain_config.model_copy(deep=True)
        candidate_config.devices[device_number] = DeviceConfig(
            device_id=payload.device_id,
            device_uuid=payload.device_uuid,
            device_number=device_number,
            mode=mode,
            rated_power=payload.rated_power,
            threshold_value=payload.threshold_value,
            desired_state=initial_desired_state,
        )

        try:
            self._persist_candidate_config(candidate_config)
        except Exception:
            logger.exception("Failed to create device_number=%s", device_number)
            return False

        actual_is_on = gpio_manager.read_is_on_by_number(device_number)

        logger.info(
            "Device created: number=%s id=%s mode=%s rated_power=%s threshold=%s "
            "requested_is_on=%s actual_is_on=%s",
            device_number,
            payload.device_id,
            mode.value,
            payload.rated_power,
            payload.threshold_value,
            requested_is_on,
            actual_is_on,
        )
        return True

    def update_device(self, payload: DeviceUpdatedPayload) -> bool:
        domain_config = domain_config_repository.load()
        device_number = int(payload.device_number)

        if device_number not in domain_config.devices:
            logger.error(
                "Cannot update device: device_number=%s not found",
                device_number,
            )
            return False

        try:
            mode = self._to_mode(payload.mode)
        except ValueError:
            logger.error("Invalid device mode for update: %s", payload.mode)
            return False

        candidate_config = domain_config.model_copy(deep=True)
        candidate_device = candidate_config.devices[device_number]
        candidate_device.device_id = payload.device_id
        if payload.device_uuid:
            candidate_device.device_uuid = payload.device_uuid
        candidate_device.device_number = device_number
        candidate_device.mode = mode

        if mode != DeviceMode.MANUAL:
            candidate_device.desired_state = None

        if "rated_power" in payload.model_fields_set:
            candidate_device.rated_power = payload.rated_power

        if "threshold_value" in payload.model_fields_set:
            candidate_device.threshold_value = payload.threshold_value

        try:
            self._persist_candidate_config(candidate_config)
        except Exception:
            logger.exception("Failed to update device_number=%s", device_number)
            return False

        if mode != DeviceMode.MANUAL and not self.sync_device_state_to_config(
            device_number=device_number
        ):
            return False

        logger.info(
            "Device updated: number=%s id=%s mode=%s rated_power=%s threshold=%s",
            device_number,
            payload.device_id,
            mode.value,
            candidate_device.rated_power,
            candidate_device.threshold_value,
        )
        return True

    def delete_device(self, payload: DeviceDeletePayload) -> bool:
        domain_config = domain_config_repository.load()
        device_number = int(payload.device_number)

        if device_number not in domain_config.devices:
            logger.error(
                "Cannot delete device: device_number=%s not found",
                device_number,
            )
            return False

        candidate_config = domain_config.model_copy(deep=True)
        candidate_config.devices.pop(device_number, None)

        try:
            self._persist_candidate_config(candidate_config)
        except Exception:
            logger.exception("Failed to delete device_number=%s", device_number)
            return False

        logger.info(
            "Device deleted: number=%s",
            device_number,
        )
        return True

    def set_manual_state(
        self, payload: DeviceCommandPayload
    ) -> Optional[RuntimeDevice]:
        device = gpio_manager.get_by_number(payload.device_number)
        if not device:
            logger.error("Device not found: %s", payload.device_number)
            return None

        device.mode = DeviceMode.MANUAL
        device.desired_state = payload.is_on

        current_state = gpio_manager.read_is_on_by_number(device.device_number)
        if current_state == payload.is_on:
            if not self.sync_device_state_to_config(
                device_number=device.device_number,
                mode_override=DeviceMode.MANUAL,
            ):
                return None
            device.desired_state = current_state
            return device

        changed = gpio_manager.set_state_by_number(
            device.device_number,
            payload.is_on,
        )

        if not changed:
            return None

        if not self.sync_device_state_to_config(
            device_number=device.device_number,
            mode_override=DeviceMode.MANUAL,
        ):
            return None

        actual_state = gpio_manager.read_is_on_by_number(device.device_number)
        device.desired_state = actual_state

        backend_adapter.log_device_event(
            device_uuid=device.device_uuid,
            device_id=device.device_id,
            device_number=device.device_number,
            event_type=DeviceEventType.STATE,
            is_on=actual_state,
            trigger_reason=DeviceTriggerReason.DEVICE_COMMAND,
        )
        self._publish_state_change_device_event_async(
            device=device,
            is_on=actual_state,
            event_type=DeviceEventType.STATE,
            trigger_reason=DeviceTriggerReason.DEVICE_COMMAND,
        )
        self._publish_heartbeat_after_state_change_async(
            device_number=device.device_number,
            trigger_reason=DeviceTriggerReason.DEVICE_COMMAND,
        )

        return device


gpio_service = GPIOService()

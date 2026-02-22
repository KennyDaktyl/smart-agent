import logging
from typing import List, Optional

from app.application.gpio_service import gpio_service
from app.core.device_event_stream_service import device_event_stream_service
from app.core.heartbeat_service import (
    HeartbeatPublishTrigger,
    heartbeat_service,
)
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import DeviceMode
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
    DeviceTriggerReason,
    backend_adapter,
)
from app.infrastructure.gpio.gpio_manager import gpio_manager

logging = logging.getLogger(__name__)


class PowerReadingService:

    @staticmethod
    def _is_auto_mode(mode: object) -> bool:
        mode_value = mode.value if hasattr(mode, "value") else str(mode)
        return mode_value == DeviceMode.AUTO.value

    def _get_auto_power_devices(self) -> List[RuntimeDevice]:
        return [
            device
            for device in gpio_manager.devices_by_number.values()
            if self._is_auto_mode(device.mode)
        ]

    @staticmethod
    def _log_backend_event(
        *,
        device: RuntimeDevice,
        is_on: bool,
        event_type: DeviceEventType,
        trigger_reason: DeviceTriggerReason,
        power_value: Optional[float],
    ) -> None:
        backend_adapter.log_device_event(
            device_uuid=device.device_uuid,
            device_id=device.device_id,
            device_number=device.device_number,
            event_type=event_type,
            is_on=is_on,
            trigger_reason=trigger_reason,
            power=power_value,
        )

    def _sync_state_or_log_error(
        self,
        *,
        device: RuntimeDevice,
        is_on: bool,
        power_value: Optional[float],
    ) -> bool:
        if gpio_service.sync_device_state_to_config(device_number=device.device_number):
            return True

        logging.error(
            "Failed to sync AUTO state to config for device_number=%s",
            device.device_number,
        )
        self._log_backend_event(
            device=device,
            is_on=is_on,
            event_type=DeviceEventType.ERROR,
            trigger_reason=DeviceTriggerReason.CONFIG_SYNC_FAILED,
            power_value=power_value,
        )
        return False

    async def _publish_state_change_device_event(
        self,
        *,
        device: RuntimeDevice,
        is_on: bool,
        event_type: DeviceEventType,
        trigger_reason: DeviceTriggerReason,
        power_value: Optional[float],
    ) -> None:
        published = await device_event_stream_service.publish_state_change(
            device=device,
            is_on=is_on,
            event_type=event_type,
            trigger_reason=trigger_reason,
            measured_value=power_value,
        )
        if not published:
            logging.warning(
                "Immediate device event publish failed for device_number=%s",
                device.device_number,
            )

    async def _publish_heartbeat_after_state_change(
        self,
        *,
        device: RuntimeDevice,
        trigger_reason: DeviceTriggerReason,
    ) -> None:
        published = await heartbeat_service.publish_now(
            trigger=HeartbeatPublishTrigger.STATE_CHANGE,
        )
        if not published:
            logging.warning(
                "Immediate heartbeat publish failed after state change "
                "| device_number=%s trigger_reason=%s",
                device.device_number,
                trigger_reason.value,
            )

    async def handle_power(
        self,
        *,
        value: Optional[float],
    ) -> None:
        logging.info("Received provider current power value=%s", value)

        auto_devices = self._get_auto_power_devices()
        if not auto_devices:
            logging.info("No AUTO devices. Nothing to do.")
            return

        power_value = value

        if power_value is None:
            logging.warning(
                "Active power missing. Forcing all AUTO devices OFF for safety."
            )
            for device in auto_devices:
                changed = gpio_manager.set_state_by_number(
                    device.device_number,
                    False,
                )
                if not changed:
                    logging.error(
                        "Failed to force OFF device_number=%s due to missing power",
                        device.device_number,
                    )
                    self._log_backend_event(
                        device=device,
                        is_on=gpio_manager.read_is_on_by_number(device.device_number),
                        event_type=DeviceEventType.ERROR,
                        trigger_reason=DeviceTriggerReason.STATE_CHANGE_FAILED,
                        power_value=power_value,
                    )
                    continue

                self._sync_state_or_log_error(
                    device=device,
                    is_on=False,
                    power_value=power_value,
                )
                self._log_backend_event(
                    device=device,
                    is_on=False,
                    event_type=DeviceEventType.ERROR,
                    trigger_reason=DeviceTriggerReason.POWER_MISSING,
                    power_value=power_value,
                )
                await self._publish_state_change_device_event(
                    device=device,
                    is_on=False,
                    event_type=DeviceEventType.ERROR,
                    trigger_reason=DeviceTriggerReason.POWER_MISSING,
                    power_value=power_value,
                )
                await self._publish_heartbeat_after_state_change(
                    device=device,
                    trigger_reason=DeviceTriggerReason.POWER_MISSING,
                )
            return

        for device in auto_devices:
            threshold = device.threshold_value
            if threshold is None:
                logging.error(
                    f"Device {device.device_number} has AUTO mode but no threshold_value."
                )
                continue

            should_turn_on = power_value >= threshold
            current_is_on = gpio_manager.read_is_on_by_number(device.device_number)

            logging.info(
                "AUTO device_number=%s threshold=%s current=%s target=%s power_value=%s",
                device.device_number,
                threshold,
                current_is_on,
                should_turn_on,
                power_value,
            )

            if current_is_on == should_turn_on:
                continue

            changed = gpio_manager.set_state_by_number(
                device.device_number,
                should_turn_on,
            )
            if not changed:
                logging.error(
                    "Failed to set state for device_number=%s target=%s",
                    device.device_number,
                    should_turn_on,
                )
                self._log_backend_event(
                    device=device,
                    is_on=current_is_on,
                    event_type=DeviceEventType.ERROR,
                    trigger_reason=DeviceTriggerReason.STATE_CHANGE_FAILED,
                    power_value=power_value,
                )
                continue

            self._sync_state_or_log_error(
                device=device,
                is_on=should_turn_on,
                power_value=power_value,
            )

            self._log_backend_event(
                device=device,
                is_on=should_turn_on,
                event_type=DeviceEventType.AUTO_TRIGGER,
                trigger_reason=DeviceTriggerReason.AUTO_TRIGGER,
                power_value=power_value,
            )
            await self._publish_state_change_device_event(
                device=device,
                is_on=should_turn_on,
                event_type=DeviceEventType.AUTO_TRIGGER,
                trigger_reason=DeviceTriggerReason.AUTO_TRIGGER,
                power_value=power_value,
            )
            await self._publish_heartbeat_after_state_change(
                device=device,
                trigger_reason=DeviceTriggerReason.AUTO_TRIGGER,
            )


power_reading_service = PowerReadingService()

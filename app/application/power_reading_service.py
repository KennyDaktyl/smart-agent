import logging
from typing import List, Optional

from app.domain.events.inverter_events import InverterProductionEvent
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import DeviceMode
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
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
    def _normalize_power_to_kw(
        power: Optional[float],
        unit: Optional[str],
    ) -> Optional[float]:
        if power is None:
            return None

        if not unit:
            return power

        normalized_unit = unit.strip().upper()
        if normalized_unit in {"W", "WATT", "WATTS"}:
            return power / 1000.0

        return power

    @staticmethod
    def _log_backend_event(
        *,
        device: RuntimeDevice,
        is_on: bool,
        event_type: DeviceEventType,
        trigger_reason: str,
        power_kw: Optional[float],
    ) -> None:
        backend_adapter.log_device_event(
            device_id=device.device_id,
            event_type=event_type,
            pin_state=is_on,
            trigger_reason=trigger_reason,
            power=power_kw,
        )

    async def handle_inverter_power(self, event: InverterProductionEvent) -> None:
        await self.handle_power(
            power=event.data.value,
            unit=event.data.unit,
        )

    async def handle_power(
        self,
        *,
        power: Optional[float],
        unit: Optional[str],
    ) -> None:
        logging.info(f"Received inverter power = {power} {unit}")

        auto_devices = self._get_auto_power_devices()
        if not auto_devices:
            logging.info("No AUTO devices. Nothing to do.")
            return

        power_kw = self._normalize_power_to_kw(power, unit)

        if power_kw is None:
            logging.warning(
                "Active power missing. Forcing all AUTO devices OFF for safety."
            )
            for device in auto_devices:
                changed = gpio_manager.set_state_by_number(
                    device.device_number,
                    False,
                )
                if changed:
                    self._log_backend_event(
                        device=device,
                        is_on=False,
                        event_type=DeviceEventType.ERROR,
                        trigger_reason="POWER_MISSING",
                        power_kw=power_kw,
                    )
            return

        for device in auto_devices:
            threshold = device.power_threshold
            if threshold is None:
                logging.error(
                    f"Device {device.device_id} has AUTO mode but no power_threshold."
                )
                continue

            should_turn_on = power_kw >= threshold
            current_is_on = gpio_manager.read_is_on_by_number(
                device.device_number
            )

            logging.info(
                "AUTO device=%s number=%s threshold=%s current=%s target=%s power_kw=%s",
                device.device_id,
                device.device_number,
                threshold,
                current_is_on,
                should_turn_on,
                power_kw,
            )

            if current_is_on == should_turn_on:
                continue

            changed = gpio_manager.set_state_by_number(
                device.device_number,
                should_turn_on,
            )
            if not changed:
                continue

            self._log_backend_event(
                device=device,
                is_on=should_turn_on,
                event_type=DeviceEventType.AUTO_TRIGGER,
                trigger_reason="AUTO_TRIGGER",
                power_kw=power_kw,
            )


power_reading_service = PowerReadingService()

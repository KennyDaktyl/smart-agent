import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("NATS_URL", "nats://localhost:4222")

from app.application.power_reading_service import PowerReadingService
from app.domain.automation_rule import (
    AutomationRuleComparator,
    AutomationRuleCondition,
    AutomationRuleGroup,
    AutomationRuleGroupOperator,
    AutomationRuleSource,
)
from app.domain.events.device_events import MetricSnapshotPayload, PowerReadingPayload
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import AgentConfig, DeviceMode


class _FakeGpioManager:
    def __init__(self, devices, initial_states):
        self.devices_by_number = {device.device_number: device for device in devices}
        self._states = dict(initial_states)

    def read_is_on_by_number(self, device_number: int) -> bool:
        return bool(self._states.get(device_number, False))

    def set_state_by_number(self, device_number: int, is_on: bool) -> bool:
        self._states[device_number] = is_on
        return True

    def get_by_number(self, device_number: int):
        return self.devices_by_number.get(device_number)


class PowerReadingServiceTests(unittest.IsolatedAsyncioTestCase):
    def _build_device(self) -> RuntimeDevice:
        return RuntimeDevice(
            device_id=1,
            device_uuid="00000000-0000-0000-0000-000000000001",
            device_number=1,
            gpio=17,
            active_low=False,
            mode=DeviceMode.AUTO,
            auto_rule=AutomationRuleGroup(
                operator=AutomationRuleGroupOperator.ANY,
                items=[
                    AutomationRuleCondition(
                        source=AutomationRuleSource.PROVIDER_BATTERY_SOC,
                        comparator=AutomationRuleComparator.GTE,
                        value=30.0,
                        unit="%",
                    )
                ],
            ),
        )

    def _build_config(self, *, has_energy_storage: bool) -> AgentConfig:
        return AgentConfig(
            microcontroller_uuid="00000000-0000-0000-0000-000000000000",
            provider_uuid="00000000-0000-0000-0000-000000000100",
            unit="kW",
            provider_has_power_meter=True,
            provider_has_energy_storage=has_energy_storage,
            heartbeat_interval=60,
            device_max=2,
            devices={},
        )

    async def test_battery_rule_turns_device_on_when_provider_supports_storage(self):
        device = self._build_device()
        fake_gpio = _FakeGpioManager([device], {1: False})
        service = PowerReadingService()

        with (
            patch(
                "app.application.power_reading_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.power_reading_service.domain_config_repository",
                SimpleNamespace(load=lambda: self._build_config(has_energy_storage=True)),
            ),
            patch(
                "app.application.power_reading_service.gpio_service",
                SimpleNamespace(sync_device_state_to_config=Mock(return_value=True)),
            ),
            patch(
                "app.application.power_reading_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.power_reading_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.power_reading_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            await service.handle_power(
                PowerReadingPayload(
                    value=0.5,
                    unit="kW",
                    battery_soc=MetricSnapshotPayload(value=45.0, unit="%"),
                )
            )

        self.assertTrue(fake_gpio.read_is_on_by_number(1))

    async def test_battery_rule_uses_telemetry_when_storage_flag_is_stale(self):
        device = self._build_device()
        fake_gpio = _FakeGpioManager([device], {1: False})
        service = PowerReadingService()

        with (
            patch(
                "app.application.power_reading_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.power_reading_service.domain_config_repository",
                SimpleNamespace(load=lambda: self._build_config(has_energy_storage=False)),
            ),
            patch(
                "app.application.power_reading_service.gpio_service",
                SimpleNamespace(sync_device_state_to_config=Mock(return_value=True)),
            ),
            patch(
                "app.application.power_reading_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.power_reading_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.power_reading_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            await service.handle_power(
                PowerReadingPayload(
                    value=0.5,
                    unit="kW",
                    battery_soc=MetricSnapshotPayload(value=45.0, unit="%"),
                )
            )

        self.assertTrue(fake_gpio.read_is_on_by_number(1))

    async def test_battery_rule_stays_off_when_soc_is_missing_and_storage_disabled(self):
        device = self._build_device()
        fake_gpio = _FakeGpioManager([device], {1: False})
        service = PowerReadingService()

        with (
            patch(
                "app.application.power_reading_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.power_reading_service.domain_config_repository",
                SimpleNamespace(load=lambda: self._build_config(has_energy_storage=False)),
            ),
            patch(
                "app.application.power_reading_service.gpio_service",
                SimpleNamespace(sync_device_state_to_config=Mock(return_value=True)),
            ),
            patch(
                "app.application.power_reading_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.power_reading_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.power_reading_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            await service.handle_power(
                PowerReadingPayload(
                    value=0.5,
                    unit="kW",
                )
            )

        self.assertFalse(fake_gpio.read_is_on_by_number(1))


if __name__ == "__main__":
    unittest.main()

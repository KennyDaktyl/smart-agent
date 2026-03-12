import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("NATS_URL", "nats://localhost:4222")

from app.application.temperature_control_service import TemperatureControlService
from app.domain.events.device_events import DeviceCommandPayload
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import DeviceMode
from app.domain.models.scheduler_policy import SchedulerControlPolicy
from app.domain.models.sensor import (
    SensorSnapshot,
    SensorStatus,
    SensorType,
    TemperatureControlConfig,
)


class _FakeGpioManager:
    def __init__(self, devices, initial_states):
        self.devices_by_number = {device.device_number: device for device in devices}
        self._states = dict(initial_states)

    def get_by_number(self, device_number: int):
        return self.devices_by_number.get(device_number)

    def read_is_on_by_number(self, device_number: int) -> bool:
        return bool(self._states.get(device_number, False))

    def set_state_by_number(self, device_number: int, is_on: bool) -> bool:
        self._states[device_number] = is_on
        return True


class TemperatureControlServiceTests(unittest.IsolatedAsyncioTestCase):
    def _build_device(self) -> RuntimeDevice:
        return RuntimeDevice(
            device_id=1,
            device_uuid="00000000-0000-0000-0000-000000000001",
            device_number=1,
            gpio=17,
            active_low=False,
            mode=DeviceMode.AUTO,
            temperature_control=TemperatureControlConfig(
                enabled=True,
                sensor_id="tank-top",
                target_temperature_c=70.0,
                stop_above_target_delta_c=2.0,
                start_below_target_delta_c=3.0,
            ),
        )

    def _snapshot(self, value: float) -> SensorSnapshot:
        return SensorSnapshot(
            sensor_id="tank-top",
            sensor_type=SensorType.DS18B20,
            value=value,
            unit="C",
            measured_at="2026-03-12T10:00:00+00:00",
            status=SensorStatus.OK,
        )

    async def test_hysteresis_threshold_decisions(self):
        config = TemperatureControlConfig(
            enabled=True,
            sensor_id="tank-top",
            target_temperature_c=70.0,
            stop_above_target_delta_c=2.0,
            start_below_target_delta_c=3.0,
        )

        self.assertTrue(
            TemperatureControlService.decide_next_state(
                current_is_on=False,
                temperature_c=67.0,
                config=config,
            )
        )
        self.assertIsNone(
            TemperatureControlService.decide_next_state(
                current_is_on=False,
                temperature_c=68.0,
                config=config,
            )
        )
        self.assertIsNone(
            TemperatureControlService.decide_next_state(
                current_is_on=True,
                temperature_c=71.0,
                config=config,
            )
        )
        self.assertFalse(
            TemperatureControlService.decide_next_state(
                current_is_on=True,
                temperature_c=72.0,
                config=config,
            )
        )

    async def test_no_clicking_inside_hysteresis_band(self):
        service = TemperatureControlService()
        device = self._build_device()
        fake_gpio = _FakeGpioManager([device], {1: False})
        snapshots = iter([67.0, 68.0, 71.0, 71.5, 72.0, 71.0, 67.0])

        with (
            patch(
                "app.application.temperature_control_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.temperature_control_service.sensor_polling_service",
                SimpleNamespace(
                    get_latest_snapshot=lambda sensor_id: self._snapshot(next(snapshots))
                ),
            ),
            patch(
                "app.application.temperature_control_service.gpio_service",
                SimpleNamespace(sync_device_state_to_config=Mock(return_value=True)),
            ),
            patch(
                "app.application.temperature_control_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.temperature_control_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.temperature_control_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            await service._evaluate_device(device)
            self.assertTrue(fake_gpio.read_is_on_by_number(1))

    async def test_scheduler_policy_command_activates_heat_up_and_force_off_on_disable(self):
        service = TemperatureControlService()
        device = self._build_device()
        fake_gpio = _FakeGpioManager([device], {1: False})
        policy = SchedulerControlPolicy(
            sensor_id="tank-top",
            target_temperature_c=65.0,
            stop_above_target_delta_c=0.0,
            start_below_target_delta_c=10.0,
            heat_up_on_activate=True,
            end_behavior="FORCE_OFF",
        )

        snapshots = iter([60.0, 60.0, 67.0, 68.0, 71.0, 72.0, 71.0, 67.0])

        with (
            patch(
                "app.application.temperature_control_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.temperature_control_service.sensor_polling_service",
                SimpleNamespace(
                    get_latest_snapshot=lambda sensor_id: self._snapshot(next(snapshots))
                ),
            ),
            patch(
                "app.application.temperature_control_service.gpio_service",
                SimpleNamespace(sync_device_state_to_config=Mock(return_value=True)),
            ),
            patch(
                "app.application.temperature_control_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.temperature_control_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.temperature_control_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            result = await service.apply_scheduler_policy_command(
                DeviceCommandPayload(
                    device_id=1,
                    device_number=1,
                    mode="SCHEDULE",
                    command="SET_SCHEDULER_POLICY",
                    is_on=False,
                    scheduler_policy_enabled=True,
                    scheduler_policy=policy,
                )
            )

            self.assertIs(result, device)
            self.assertTrue(fake_gpio.read_is_on_by_number(1))

            result = await service.apply_scheduler_policy_command(
                DeviceCommandPayload(
                    device_id=1,
                    device_number=1,
                    mode="SCHEDULE",
                    command="SET_SCHEDULER_POLICY",
                    is_on=False,
                    scheduler_policy_enabled=False,
                    scheduler_policy=policy,
                )
            )

            self.assertIs(result, device)
            self.assertFalse(fake_gpio.read_is_on_by_number(1))

            await service._evaluate_device(device)
            self.assertTrue(fake_gpio.read_is_on_by_number(1))

            await service._evaluate_device(device)
            self.assertTrue(fake_gpio.read_is_on_by_number(1))

            await service._evaluate_device(device)
            self.assertTrue(fake_gpio.read_is_on_by_number(1))

            await service._evaluate_device(device)
            self.assertFalse(fake_gpio.read_is_on_by_number(1))

            await service._evaluate_device(device)
            self.assertFalse(fake_gpio.read_is_on_by_number(1))

            await service._evaluate_device(device)
            self.assertTrue(fake_gpio.read_is_on_by_number(1))


if __name__ == "__main__":
    unittest.main()

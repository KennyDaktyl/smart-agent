import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("NATS_URL", "nats://localhost:4222")
sys.modules.setdefault(
    "nats",
    types.SimpleNamespace(connect=AsyncMock()),
)

from app.application.device_dependency_service import DeviceDependencyService
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import DeviceMode
from app.domain.models.device_dependency import DeviceDependencyRule


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
        device = self.get_by_number(device_number)
        if device is not None:
            device.desired_state = is_on
        return True

    def set_runtime_override_by_number(self, device_number: int, is_on: bool) -> bool:
        self._states[device_number] = is_on
        return True


class DeviceDependencyServiceTests(unittest.IsolatedAsyncioTestCase):
    def _build_auto_source(self) -> RuntimeDevice:
        return RuntimeDevice(
            device_id=1,
            device_uuid="00000000-0000-0000-0000-000000000001",
            device_number=1,
            gpio=17,
            active_low=False,
            mode=DeviceMode.AUTO,
            device_dependency_rule=DeviceDependencyRule(
                target_device_id=2,
                target_device_number=2,
                when_source_on="OFF",
                when_source_off="NONE",
            ),
        )

    def _build_scheduler_source(self) -> RuntimeDevice:
        return RuntimeDevice(
            device_id=1,
            device_uuid="00000000-0000-0000-0000-000000000001",
            device_number=1,
            gpio=17,
            active_low=False,
            mode=DeviceMode.SCHEDULE,
        )

    def _build_manual_target(self, *, desired_state: bool) -> RuntimeDevice:
        return RuntimeDevice(
            device_id=2,
            device_uuid="00000000-0000-0000-0000-000000000002",
            device_number=2,
            gpio=27,
            active_low=False,
            mode=DeviceMode.MANUAL,
            desired_state=desired_state,
        )

    async def test_auto_source_forces_target_off_and_restores_manual_target(self):
        service = DeviceDependencyService()
        source = self._build_auto_source()
        target = self._build_manual_target(desired_state=True)
        fake_gpio = _FakeGpioManager([source, target], {1: False, 2: True})

        with (
            patch(
                "app.application.device_dependency_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.device_dependency_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.device_dependency_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.device_dependency_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            fake_gpio.set_state_by_number(1, True)
            changed = service.handle_source_state_change(source_device_number=1)
            self.assertTrue(changed)
            self.assertFalse(fake_gpio.read_is_on_by_number(2))
            self.assertTrue(target.desired_state)

            fake_gpio.set_state_by_number(1, False)
            changed = service.handle_source_state_change(source_device_number=1)
            self.assertTrue(changed)
            self.assertTrue(fake_gpio.read_is_on_by_number(2))

    async def test_scheduler_rule_forces_target_and_release_restores_manual_state(self):
        service = DeviceDependencyService()
        source = self._build_scheduler_source()
        target = self._build_manual_target(desired_state=False)
        fake_gpio = _FakeGpioManager([source, target], {1: False, 2: False})
        scheduler_rule = DeviceDependencyRule(
            target_device_id=2,
            target_device_number=2,
            when_source_on="ON",
            when_source_off="OFF",
        )

        with (
            patch(
                "app.application.device_dependency_service.gpio_manager",
                fake_gpio,
            ),
            patch(
                "app.application.device_dependency_service.backend_adapter",
                SimpleNamespace(log_device_event=Mock()),
            ),
            patch(
                "app.application.device_dependency_service.device_event_stream_service",
                SimpleNamespace(publish_state_change=AsyncMock(return_value=True)),
            ),
            patch(
                "app.application.device_dependency_service.heartbeat_service",
                SimpleNamespace(publish_now=AsyncMock(return_value=True)),
            ),
        ):
            service.set_scheduler_rule(source_device_number=1, rule=scheduler_rule)

            fake_gpio.set_state_by_number(1, True)
            changed = service.handle_source_state_change(source_device_number=1)
            self.assertTrue(changed)
            self.assertTrue(fake_gpio.read_is_on_by_number(2))
            self.assertFalse(target.desired_state)

            cleared_rule = service.clear_scheduler_rule(source_device_number=1)
            self.assertIsNotNone(cleared_rule)
            changed = service.reconcile_target(target_device_number=2)
            self.assertTrue(changed)
            self.assertFalse(fake_gpio.read_is_on_by_number(2))


if __name__ == "__main__":
    unittest.main()

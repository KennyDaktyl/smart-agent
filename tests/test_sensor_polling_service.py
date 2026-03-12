import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("NATS_URL", "nats://localhost:4222")

from app.application.sensor_polling_service import (
    DEFAULT_TEMPERATURE_SENSOR_ALIAS,
    PublishedSensorState,
    SensorPollingService,
)
from app.domain.models.agent_config import AgentConfig
from app.domain.models.hardware_config import HardwareConfig
from app.domain.models.sensor import SensorSnapshot, SensorStatus, SensorType
from app.infrastructure.sensors.ds18b20_reader import parse_ds18b20_temperature_c


class SensorPollingServiceTests(unittest.TestCase):
    def _build_domain_config(self, *, available_sensors: list[str]) -> AgentConfig:
        return AgentConfig(
            microcontroller_uuid="00000000-0000-0000-0000-000000000000",
            provider_uuid="00000000-0000-0000-0000-000000000100",
            available_sensors=available_sensors,
            devices={},
        )

    def _build_hardware_config(self, *, include_sensor: bool) -> HardwareConfig:
        sensors = (
            {
                "tank-top": {
                    "type": "ds18b20",
                    "address": "28-000000000001",
                    "unit": "C",
                }
            }
            if include_sensor
            else {}
        )
        return HardwareConfig(
            devices={},
            sensors=sensors,
        )

    def test_service_is_disabled_when_available_sensors_is_empty(self):
        service = SensorPollingService()
        with (
            patch(
                "app.application.sensor_polling_service.domain_config_repository",
                SimpleNamespace(
                    load=lambda: self._build_domain_config(available_sensors=[])
                ),
            ),
            patch(
                "app.application.sensor_polling_service.hardware_config_repository",
                SimpleNamespace(
                    load=lambda: self._build_hardware_config(include_sensor=True)
                ),
            ),
        ):
            self.assertEqual(service.resolve_active_sensor_configs(), [])

    def test_service_is_disabled_when_hardware_has_no_physical_sensors(self):
        service = SensorPollingService()
        with (
            patch(
                "app.application.sensor_polling_service.domain_config_repository",
                SimpleNamespace(
                    load=lambda: self._build_domain_config(
                        available_sensors=["ds18b20"]
                    )
                ),
            ),
            patch(
                "app.application.sensor_polling_service.hardware_config_repository",
                SimpleNamespace(
                    load=lambda: self._build_hardware_config(include_sensor=False)
                ),
            ),
        ):
            self.assertEqual(service.resolve_active_sensor_configs(), [])

    def test_publish_happens_only_on_threshold_change_or_timeout(self):
        now = datetime.now(timezone.utc)
        previous = PublishedSensorState(
            value=70.0,
            status="OK",
            published_at=now,
        )

        small_change_snapshot = SensorSnapshot(
            sensor_id="tank-top",
            sensor_type=SensorType.DS18B20,
            value=70.3,
            unit="C",
            measured_at=now.isoformat(),
            status=SensorStatus.OK,
        )
        threshold_change_snapshot = small_change_snapshot.model_copy(
            update={"value": 70.5}
        )
        timeout_snapshot = small_change_snapshot.model_copy(update={"value": 70.1})

        self.assertFalse(
            SensorPollingService.should_publish_snapshot(
                snapshot=small_change_snapshot,
                previous_state=previous,
                publish_interval_sec=60.0,
                change_threshold_c=0.5,
                now=now + timedelta(seconds=10),
            )
        )
        self.assertTrue(
            SensorPollingService.should_publish_snapshot(
                snapshot=threshold_change_snapshot,
                previous_state=previous,
                publish_interval_sec=60.0,
                change_threshold_c=0.5,
                now=now + timedelta(seconds=10),
            )
        )
        self.assertTrue(
            SensorPollingService.should_publish_snapshot(
                snapshot=timeout_snapshot,
                previous_state=previous,
                publish_interval_sec=60.0,
                change_threshold_c=0.5,
                now=now + timedelta(seconds=61),
            )
        )

    def test_ds18b20_parser_normalizes_value_and_applies_offset(self):
        raw_contents = (
            "5b 01 4b 46 7f ff 05 10 6f : crc=6f YES\n"
            "5b 01 4b 46 7f ff 05 10 6f t=21937\n"
        )

        self.assertEqual(
            parse_ds18b20_temperature_c(raw_contents, offset_c=0.5),
            22.44,
        )

    def test_temperature_alias_resolves_first_temperature_snapshot(self):
        service = SensorPollingService()
        service._sensor_snapshots = {
            "tank-bottom": SensorSnapshot(
                sensor_id="tank-bottom",
                sensor_type=SensorType.DS18B20,
                value=58.0,
                unit="C",
                measured_at=datetime.now(timezone.utc).isoformat(),
                status=SensorStatus.OK,
            ),
            "tank-top": SensorSnapshot(
                sensor_id="tank-top",
                sensor_type=SensorType.DS18B20,
                value=61.0,
                unit="C",
                measured_at=datetime.now(timezone.utc).isoformat(),
                status=SensorStatus.OK,
            ),
        }

        resolved = service.get_latest_snapshot(DEFAULT_TEMPERATURE_SENSOR_ALIAS)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.sensor_id, "tank-bottom")


if __name__ == "__main__":
    unittest.main()

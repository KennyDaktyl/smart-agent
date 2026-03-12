import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("NATS_URL", "nats://localhost:4222")

from app.core.heartbeat_service import heartbeat_service
from app.domain.models.agent_config import AgentConfig


class AgentConfigSensorsTests(unittest.TestCase):
    def test_available_sensors_are_normalized_and_deduplicated(self):
        config = AgentConfig(
            microcontroller_uuid="00000000-0000-0000-0000-000000000000",
            provider_uuid="00000000-0000-0000-0000-000000000100",
            available_sensors=[" DS18B20 ", "dht22", "ds18b20", ""],
            devices={},
        )

        self.assertEqual(config.available_sensors, ["ds18b20", "dht22"])

    def test_heartbeat_payload_includes_available_sensors(self):
        config = AgentConfig(
            microcontroller_uuid="00000000-0000-0000-0000-000000000000",
            provider_uuid="00000000-0000-0000-0000-000000000100",
            heartbeat_interval=60,
            available_sensors=["ds18b20"],
            devices={},
        )

        heartbeat_service._micro_uuid = config.microcontroller_uuid
        heartbeat_service._interval = config.heartbeat_interval

        with (
            patch(
                "app.core.heartbeat_service.domain_config_repository",
                SimpleNamespace(load=lambda: config),
            ),
            patch(
                "app.core.heartbeat_service.gpio_manager",
                SimpleNamespace(get_devices_status=lambda: []),
            ),
        ):
            payload = heartbeat_service._build_heartbeat_payload()

        self.assertEqual(payload["available_sensors"], ["ds18b20"])
        self.assertEqual(payload["uuid"], config.microcontroller_uuid)


if __name__ == "__main__":
    unittest.main()

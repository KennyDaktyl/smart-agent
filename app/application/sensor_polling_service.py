from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.nats_client import nats_client
from app.core.nats_subjects import AgentEvents, NatsSubjects
from app.domain.events.enums import EventType
from app.domain.models.sensor import (
    HardwareSensorConfig,
    SensorSnapshot,
    SensorStatus,
    SensorType,
)
from app.infrastructure.config.domain_config_repository import domain_config_repository
from app.infrastructure.config.hardware_config_repository import (
    hardware_config_repository,
)
from app.infrastructure.sensors.ds18b20_reader import read_ds18b20_temperature_c

logger = logging.getLogger(__name__)

SUPPORTED_SENSOR_TYPES = {SensorType.DS18B20.value}
DEFAULT_POLL_INTERVAL_SEC = 5.0
DEFAULT_PUBLISH_INTERVAL_SEC = 60.0
DEFAULT_CHANGE_THRESHOLD_C = 0.5
DEFAULT_TEMPERATURE_SENSOR_ALIAS = "temperature"


@dataclass
class PublishedSensorState:
    value: float | None
    status: str
    published_at: datetime


class SensorPollingService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._sensor_snapshots: dict[str, SensorSnapshot] = {}
        self._last_published: dict[str, PublishedSensorState] = {}
        self._disabled_logged = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="sensor-polling")

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def get_sensor_snapshots(self) -> list[dict]:
        return [
            snapshot.model_dump(mode="json")
            for snapshot in sorted(
                self._sensor_snapshots.values(),
                key=lambda snapshot: snapshot.sensor_id,
            )
        ]

    def get_latest_snapshot(self, sensor_id: str) -> SensorSnapshot | None:
        normalized_sensor_id = str(sensor_id).strip()
        if not normalized_sensor_id:
            return None

        snapshot = self._sensor_snapshots.get(normalized_sensor_id)
        if snapshot is not None:
            return snapshot

        if normalized_sensor_id.lower() != DEFAULT_TEMPERATURE_SENSOR_ALIAS:
            return None

        temperature_snapshots = sorted(
            (
                candidate
                for candidate in self._sensor_snapshots.values()
                if candidate.sensor_type == SensorType.DS18B20
            ),
            key=lambda candidate: candidate.sensor_id,
        )
        return temperature_snapshots[0] if temperature_snapshots else None

    def resolve_active_sensor_configs(self) -> list[HardwareSensorConfig]:
        domain_config = domain_config_repository.load()
        hardware_config = hardware_config_repository.load()

        if not domain_config.available_sensors:
            return []
        if not hardware_config.sensors:
            return []

        available_sensor_types = {
            sensor_type
            for sensor_type in domain_config.available_sensors
            if sensor_type in SUPPORTED_SENSOR_TYPES
        }
        if not available_sensor_types:
            return []

        return [
            sensor
            for sensor in hardware_config.sensors.values()
            if sensor.type.value in available_sensor_types
        ]

    @staticmethod
    def _status_value(snapshot: SensorSnapshot) -> str:
        status = snapshot.status
        return status.value if hasattr(status, "value") else str(status)

    @staticmethod
    def should_publish_snapshot(
        *,
        snapshot: SensorSnapshot,
        previous_state: PublishedSensorState | None,
        publish_interval_sec: float,
        change_threshold_c: float,
        now: datetime,
    ) -> bool:
        if previous_state is None:
            return True
        current_status = SensorPollingService._status_value(snapshot)
        if previous_state.status != current_status:
            return True

        elapsed_sec = (now - previous_state.published_at).total_seconds()
        if elapsed_sec >= publish_interval_sec:
            return True

        if snapshot.value is None or previous_state.value is None:
            return False

        return abs(snapshot.value - previous_state.value) >= change_threshold_c

    async def _loop(self) -> None:
        while self._running:
            poll_interval_sec = DEFAULT_POLL_INTERVAL_SEC
            try:
                domain_config = domain_config_repository.load()
                poll_interval_sec = max(
                    1.0,
                    float(
                        getattr(
                            domain_config,
                            "sensor_poll_interval_sec",
                            DEFAULT_POLL_INTERVAL_SEC,
                        )
                    ),
                )
                publish_interval_sec = max(
                    1.0,
                    float(
                        getattr(
                            domain_config,
                            "sensor_publish_interval_sec",
                            DEFAULT_PUBLISH_INTERVAL_SEC,
                        )
                    ),
                )
                change_threshold_c = max(
                    0.0,
                    float(
                        getattr(
                            domain_config,
                            "sensor_change_threshold_c",
                            DEFAULT_CHANGE_THRESHOLD_C,
                        )
                    ),
                )
                active_sensors = self.resolve_active_sensor_configs()

                if not active_sensors:
                    if not self._disabled_logged:
                        logger.info("sensor service disabled")
                    self._disabled_logged = True
                    self._sensor_snapshots = {}
                    self._last_published = {}
                    await asyncio.sleep(poll_interval_sec)
                    continue

                self._disabled_logged = False
                for sensor in active_sensors:
                    snapshot = await self._read_sensor_snapshot(sensor)
                    self._sensor_snapshots[sensor.sensor_id] = snapshot
                    await self._publish_snapshot_if_due(
                        microcontroller_uuid=domain_config.microcontroller_uuid,
                        snapshot=snapshot,
                        publish_interval_sec=publish_interval_sec,
                        change_threshold_c=change_threshold_c,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("sensor polling loop failed")

            await asyncio.sleep(poll_interval_sec)

    async def _read_sensor_snapshot(
        self,
        sensor: HardwareSensorConfig,
    ) -> SensorSnapshot:
        measured_at = datetime.now(timezone.utc).isoformat()
        try:
            if sensor.type == SensorType.DS18B20:
                value = await asyncio.to_thread(
                    read_ds18b20_temperature_c,
                    address=sensor.address,
                    offset_c=sensor.offset_c,
                )
            else:
                raise ValueError(f"Unsupported sensor type: {sensor.type.value}")

            return SensorSnapshot(
                sensor_id=sensor.sensor_id,
                sensor_type=sensor.type,
                value=value,
                unit=sensor.unit,
                measured_at=measured_at,
                status=SensorStatus.OK,
            )
        except Exception:
            logger.exception(
                "sensor read failed | sensor_id=%s sensor_type=%s",
                sensor.sensor_id,
                sensor.type.value,
            )
            return SensorSnapshot(
                sensor_id=sensor.sensor_id,
                sensor_type=sensor.type,
                value=None,
                unit=sensor.unit,
                measured_at=measured_at,
                status=SensorStatus.ERROR,
            )

    async def _publish_snapshot_if_due(
        self,
        *,
        microcontroller_uuid: str,
        snapshot: SensorSnapshot,
        publish_interval_sec: float,
        change_threshold_c: float,
    ) -> None:
        now = datetime.now(timezone.utc)
        previous_state = self._last_published.get(snapshot.sensor_id)
        if not self.should_publish_snapshot(
            snapshot=snapshot,
            previous_state=previous_state,
            publish_interval_sec=publish_interval_sec,
            change_threshold_c=change_threshold_c,
            now=now,
        ):
            return

        subject = NatsSubjects.agent_event(
            microcontroller_uuid,
            AgentEvents.SENSOR_READING,
        )
        payload = {
            "microcontroller_uuid": microcontroller_uuid,
            **snapshot.model_dump(mode="json"),
        }
        event = {
            "event_type": EventType.SENSOR_READING.value,
            "subject": subject,
            "payload": payload,
        }

        logger.info(
            "Publishing sensor snapshot | subject=%s sensor_id=%s status=%s value=%s",
            subject,
            snapshot.sensor_id,
            self._status_value(snapshot),
            snapshot.value,
        )
        await nats_client.js_publish(subject, event)
        self._last_published[snapshot.sensor_id] = PublishedSensorState(
            value=snapshot.value,
            status=self._status_value(snapshot),
            published_at=now,
        )


sensor_polling_service = SensorPollingService()

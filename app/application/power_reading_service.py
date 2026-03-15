import logging
from typing import List, Optional

from app.application.device_dependency_service import device_dependency_service
from app.application.gpio_service import gpio_service
from app.core.device_event_stream_service import device_event_stream_service
from app.core.heartbeat_service import (
    HeartbeatPublishTrigger,
    heartbeat_service,
)
from app.domain.automation_rule import (
    AutomationRuleGroup,
    AutomationRuleSource,
    MatchedCondition,
    MetricSnapshot,
    build_legacy_power_rule,
    evaluate_rule,
    find_first_matching_condition,
    iter_conditions,
)
from app.domain.events.device_events import PowerReadingPayload
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import AgentConfig, DeviceMode
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
    DeviceTriggerReason,
    backend_adapter,
)
from app.infrastructure.config.domain_config_repository import domain_config_repository
from app.infrastructure.gpio.gpio_manager import gpio_manager

logging = logging.getLogger(__name__)
BATTERY_SOC_METRIC_KEY = "battery_soc"


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
        power_unit: Optional[str] = None,
        measured_value: Optional[float] = None,
        measured_unit: Optional[str] = None,
    ) -> None:
        backend_adapter.log_device_event(
            device_uuid=device.device_uuid,
            device_id=device.device_id,
            device_number=device.device_number,
            event_type=event_type,
            is_on=is_on,
            trigger_reason=trigger_reason,
            power=power_value,
            power_unit=power_unit,
            measured_value=measured_value,
            measured_unit=measured_unit,
        )

    def _sync_state_or_log_error(
        self,
        *,
        device: RuntimeDevice,
        is_on: bool,
        power_value: Optional[float],
        power_unit: Optional[str] = None,
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
            power_unit=power_unit,
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
        power_unit: Optional[str] = None,
        measured_value: Optional[float] = None,
        measured_unit: Optional[str] = None,
    ) -> None:
        published = await device_event_stream_service.publish_state_change(
            device=device,
            is_on=is_on,
            event_type=event_type,
            trigger_reason=trigger_reason,
            measured_value=measured_value if measured_value is not None else power_value,
            measured_unit=measured_unit if measured_value is not None else power_unit,
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

    def _resolve_auto_rule(self, device: RuntimeDevice) -> AutomationRuleGroup | None:
        if device.auto_rule is not None:
            return device.auto_rule
        if device.threshold_value is None:
            return None

        return build_legacy_power_rule(
            value=float(device.threshold_value),
            unit=device.threshold_unit or "W",
        )

    @staticmethod
    def _resolve_trigger_measurement(
        *,
        rule: AutomationRuleGroup,
        measurements: dict[AutomationRuleSource, MetricSnapshot | None],
    ) -> MatchedCondition | None:
        return find_first_matching_condition(rule, measurements)

    @staticmethod
    def _normalize_unit(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        normalized = value.strip()
        return normalized or None

    def _extract_extra_metric(
        self,
        payload: PowerReadingPayload,
        metric_key: str,
    ) -> MetricSnapshot | None:
        for metric in payload.extra_metrics or []:
            if not isinstance(metric, dict):
                continue
            current_key = metric.get("key")
            if current_key is None:
                current_key = metric.get("metric_key")
            if current_key != metric_key:
                continue
            value = metric.get("value")
            if value is None:
                return None
            try:
                return MetricSnapshot(
                    value=float(value),
                    unit=self._normalize_unit(metric.get("unit")),
                )
            except (TypeError, ValueError):
                return None
        return None

    def _build_measurements(
        self,
        payload: PowerReadingPayload,
    ) -> dict[AutomationRuleSource, MetricSnapshot | None]:
        battery_metric = None
        if payload.battery_soc and payload.battery_soc.value is not None:
            battery_metric = MetricSnapshot(
                value=float(payload.battery_soc.value),
                unit=self._normalize_unit(payload.battery_soc.unit) or "%",
            )
        if battery_metric is None:
            battery_metric = self._extract_extra_metric(payload, BATTERY_SOC_METRIC_KEY)

        primary_power_metric = None
        if payload.value is not None:
            primary_power_metric = MetricSnapshot(
                value=float(payload.value),
                unit=self._normalize_unit(payload.unit),
            )

        return {
            AutomationRuleSource.PROVIDER_PRIMARY_POWER: primary_power_metric,
            AutomationRuleSource.PROVIDER_BATTERY_SOC: battery_metric,
        }

    @staticmethod
    def _has_metric(
        measurements: dict[AutomationRuleSource, MetricSnapshot | None],
        source: AutomationRuleSource,
    ) -> bool:
        return measurements.get(source) is not None

    def _has_missing_required_metrics(
        self,
        *,
        rule: AutomationRuleGroup,
        measurements: dict[AutomationRuleSource, MetricSnapshot | None],
        config: AgentConfig,
    ) -> bool:
        for condition in iter_conditions(rule):
            if (
                condition.source == AutomationRuleSource.PROVIDER_BATTERY_SOC
                and not config.provider_has_energy_storage
                and self._has_metric(measurements, condition.source)
            ):
                continue
            if not self._has_metric(measurements, condition.source):
                return True
        return False

    async def handle_power(
        self,
        payload: PowerReadingPayload,
    ) -> None:
        logging.info(
            "Received provider telemetry value=%s unit=%s battery_soc=%s",
            payload.value,
            payload.unit,
            payload.battery_soc.value if payload.battery_soc else None,
        )

        auto_devices = self._get_auto_power_devices()
        if not auto_devices:
            logging.info("No AUTO devices. Nothing to do.")
            return

        domain_config = domain_config_repository.load()
        measurements = self._build_measurements(payload)
        power_value = payload.value
        power_unit = payload.unit
        battery_value = (
            measurements[AutomationRuleSource.PROVIDER_BATTERY_SOC].value
            if measurements.get(AutomationRuleSource.PROVIDER_BATTERY_SOC) is not None
            else None
        )
        has_battery_soc = self._has_metric(
            measurements,
            AutomationRuleSource.PROVIDER_BATTERY_SOC,
        )

        if has_battery_soc and not domain_config.provider_has_energy_storage:
            logging.warning(
                "Provider telemetry contains battery_soc despite "
                "provider_has_energy_storage=false in agent config. "
                "Treating battery_soc as available telemetry."
            )

        for device in auto_devices:
            rule = self._resolve_auto_rule(device)
            if rule is None:
                logging.error(
                    "Device %s has AUTO mode but no threshold_value or auto_rule.",
                    device.device_number,
                )
                continue

            if (
                not domain_config.provider_has_energy_storage
                and any(
                    condition.source == AutomationRuleSource.PROVIDER_BATTERY_SOC
                    for condition in iter_conditions(rule)
                )
                and not has_battery_soc
            ):
                logging.warning(
                    "AUTO rule references provider_battery_soc but provider does not "
                    "support energy storage | device_number=%s",
                    device.device_number,
                )

            should_turn_on = evaluate_rule(rule, measurements)
            matched_condition = (
                self._resolve_trigger_measurement(rule=rule, measurements=measurements)
                if should_turn_on
                else None
            )
            effective_target_state = device_dependency_service.resolve_requested_state(
                device_number=device.device_number,
                requested_state=should_turn_on,
            )
            current_is_on = gpio_manager.read_is_on_by_number(device.device_number)

            logging.info(
                "AUTO device_number=%s current=%s target=%s power_value=%s "
                "battery_soc=%s matched_source=%s matched_value=%s matched_unit=%s",
                device.device_number,
                current_is_on,
                should_turn_on,
                power_value,
                battery_value,
                matched_condition.condition.source.value
                if matched_condition is not None
                else None,
                matched_condition.measured_value if matched_condition is not None else None,
                matched_condition.measured_unit if matched_condition is not None else None,
            )

            if current_is_on == effective_target_state:
                continue

            changed = gpio_manager.set_state_by_number(
                device.device_number,
                effective_target_state,
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
                    power_unit=power_unit,
                    measured_value=(
                        matched_condition.measured_value
                        if matched_condition is not None
                        else None
                    ),
                    measured_unit=(
                        matched_condition.measured_unit
                        if matched_condition is not None
                        else None
                    ),
                )
                continue

            self._sync_state_or_log_error(
                device=device,
                is_on=effective_target_state,
                power_value=power_value,
                power_unit=power_unit,
            )
            device_dependency_service.handle_source_state_change(
                source_device_number=device.device_number
            )

            trigger_reason = DeviceTriggerReason.AUTO_TRIGGER
            event_type = DeviceEventType.AUTO_TRIGGER
            if (
                not effective_target_state
                and self._has_missing_required_metrics(
                    rule=rule,
                    measurements=measurements,
                    config=domain_config,
                )
            ):
                trigger_reason = DeviceTriggerReason.POWER_MISSING
                event_type = DeviceEventType.ERROR

            self._log_backend_event(
                device=device,
                is_on=effective_target_state,
                event_type=event_type,
                trigger_reason=trigger_reason,
                power_value=power_value,
                power_unit=power_unit,
                measured_value=(
                    matched_condition.measured_value
                    if matched_condition is not None
                    else None
                ),
                measured_unit=(
                    matched_condition.measured_unit
                    if matched_condition is not None
                    else None
                ),
            )
            await self._publish_state_change_device_event(
                device=device,
                is_on=effective_target_state,
                event_type=event_type,
                trigger_reason=trigger_reason,
                power_value=power_value,
                power_unit=power_unit,
                measured_value=(
                    matched_condition.measured_value
                    if matched_condition is not None
                    else None
                ),
                measured_unit=(
                    matched_condition.measured_unit
                    if matched_condition is not None
                    else None
                ),
            )
            await self._publish_heartbeat_after_state_change(
                device=device,
                trigger_reason=trigger_reason,
            )


power_reading_service = PowerReadingService()

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from app.application.device_dependency_service import device_dependency_service
from app.application.gpio_service import gpio_service
from app.application.sensor_polling_service import sensor_polling_service
from app.core.device_event_stream_service import device_event_stream_service
from app.core.heartbeat_service import (
    HeartbeatPublishTrigger,
    heartbeat_service,
)
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.events.device_events import DeviceCommandPayload
from app.domain.models.scheduler_policy import (
    ActiveSchedulerPolicy,
    SchedulerControlPolicy,
    SchedulerPolicyEndBehavior,
    SchedulerTemperaturePhase,
)
from app.domain.models.sensor import SensorStatus, TemperatureControlConfig
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
    DeviceTriggerReason,
    backend_adapter,
)
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)

CONTROL_LOOP_INTERVAL_SEC = 1.0


class TemperatureControlService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._active_scheduler_policies: dict[int, ActiveSchedulerPolicy] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._loop(),
            name="temperature-control",
        )

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

    @staticmethod
    def decide_next_state(
        *,
        current_is_on: bool,
        temperature_c: float,
        config: TemperatureControlConfig,
    ) -> bool | None:
        start_threshold_c = config.start_threshold_c
        stop_threshold_c = config.stop_threshold_c
        if start_threshold_c is None or stop_threshold_c is None:
            return None

        if current_is_on and temperature_c >= stop_threshold_c:
            return False
        if (not current_is_on) and temperature_c <= start_threshold_c:
            return True
        return None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._evaluate_devices()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("temperature control loop failed")
            await asyncio.sleep(CONTROL_LOOP_INTERVAL_SEC)

    async def _evaluate_devices(self) -> None:
        for device in list(gpio_manager.devices_by_number.values()):
            await self._evaluate_device(device)

    async def apply_scheduler_policy_command(
        self,
        payload: DeviceCommandPayload,
    ) -> RuntimeDevice | None:
        device = gpio_manager.get_by_number(payload.device_number)
        if device is None:
            logger.error(
                "scheduler policy command for unknown device_number=%s",
                payload.device_number,
            )
            return None

        if payload.scheduler_policy_enabled:
            if payload.scheduler_policy is None:
                logger.error(
                    "scheduler policy enable without policy payload | device_number=%s",
                    payload.device_number,
                )
                return None
            await self._activate_scheduler_policy(
                device=device,
                policy=payload.scheduler_policy,
                dependency_rule=payload.device_dependency_rule,
            )
            return device

        await self._deactivate_scheduler_policy(
            device=device,
            policy=payload.scheduler_policy,
            dependency_rule=payload.device_dependency_rule,
        )
        return device

    async def _activate_scheduler_policy(
        self,
        *,
        device: RuntimeDevice,
        policy: SchedulerControlPolicy,
        dependency_rule,
    ) -> None:
        existing = self._active_scheduler_policies.get(device.device_number)
        if existing is not None and existing.policy == policy:
            return

        snapshot = sensor_polling_service.get_latest_snapshot(policy.sensor_id)
        phase = SchedulerTemperaturePhase.HEAT_UP
        if (
            not policy.heat_up_on_activate
            or (
                snapshot is not None
                and snapshot.value is not None
                and snapshot.status == SensorStatus.OK
                and snapshot.value >= policy.stop_threshold_c
            )
        ):
            phase = SchedulerTemperaturePhase.HOLD

        self._active_scheduler_policies[device.device_number] = ActiveSchedulerPolicy(
            policy=policy,
            phase=phase,
        )
        device_dependency_service.set_scheduler_rule(
            source_device_number=device.device_number,
            rule=dependency_rule,
        )
        await self._publish_scheduler_policy_event(
            device=device,
            trigger_reason=DeviceTriggerReason.SCHEDULER_POLICY_ENABLED,
        )
        device_dependency_service.handle_source_state_change(
            source_device_number=device.device_number
        )
        await self._evaluate_device(device)

    async def _deactivate_scheduler_policy(
        self,
        *,
        device: RuntimeDevice,
        policy: SchedulerControlPolicy | None,
        dependency_rule,
    ) -> None:
        active = self._active_scheduler_policies.pop(device.device_number, None)
        effective_policy = policy or (active.policy if active is not None else None)
        cleared_rule = device_dependency_service.clear_scheduler_rule(
            source_device_number=device.device_number
        )
        effective_dependency_rule = dependency_rule or cleared_rule

        if (
            effective_policy is not None
            and effective_policy.end_behavior == SchedulerPolicyEndBehavior.FORCE_OFF
        ):
            current_is_on = gpio_manager.read_is_on_by_number(device.device_number)
            if current_is_on:
                next_state = device_dependency_service.resolve_requested_state(
                    device_number=device.device_number,
                    requested_state=False,
                )
                changed = gpio_manager.set_state_by_number(device.device_number, next_state)
                if changed:
                    gpio_service.sync_device_state_to_config(
                        device_number=device.device_number
                    )
                    device_dependency_service.handle_source_state_change(
                        source_device_number=device.device_number
                    )

        if effective_dependency_rule is not None:
            device_dependency_service.reconcile_target(
                target_device_number=effective_dependency_rule.target_device_number
            )

        await self._publish_scheduler_policy_event(
            device=device,
            trigger_reason=DeviceTriggerReason.SCHEDULER_POLICY_DISABLED,
        )

    async def _publish_scheduler_policy_event(
        self,
        *,
        device: RuntimeDevice,
        trigger_reason: DeviceTriggerReason | str,
        measured_value: float | None = None,
        measured_unit: str | None = None,
    ) -> None:
        actual_state = gpio_manager.read_is_on_by_number(device.device_number)
        backend_adapter.log_device_event(
            device_uuid=device.device_uuid,
            device_id=device.device_id,
            device_number=device.device_number,
            event_type=DeviceEventType.SCHEDULER,
            is_on=actual_state,
            trigger_reason=trigger_reason,
            measured_value=measured_value,
            measured_unit=measured_unit,
        )
        await device_event_stream_service.publish_state_change(
            device=device,
            is_on=actual_state,
            event_type=DeviceEventType.SCHEDULER,
            trigger_reason=trigger_reason,
            measured_value=measured_value,
            measured_unit=measured_unit or "C",
        )
        await heartbeat_service.publish_now(trigger=HeartbeatPublishTrigger.STATE_CHANGE)

    async def _evaluate_device(self, device: RuntimeDevice) -> None:
        active_policy = self._active_scheduler_policies.get(device.device_number)
        if active_policy is not None:
            await self._evaluate_scheduler_policy_device(
                device=device,
                active_policy=active_policy,
            )
            return
        control = device.temperature_control
        if control is None or not control.enabled or control.sensor_id is None:
            return

        snapshot = sensor_polling_service.get_latest_snapshot(control.sensor_id)
        if snapshot is None:
            return
        if snapshot.status != SensorStatus.OK or snapshot.value is None:
            return

        current_is_on = gpio_manager.read_is_on_by_number(device.device_number)
        next_state = self.decide_next_state(
            current_is_on=current_is_on,
            temperature_c=snapshot.value,
            config=control,
        )
        if next_state is None or next_state == current_is_on:
            return

        next_state = device_dependency_service.resolve_requested_state(
            device_number=device.device_number,
            requested_state=next_state,
        )
        if next_state == current_is_on:
            return

        changed = gpio_manager.set_state_by_number(device.device_number, next_state)
        if not changed:
            logger.error(
                "temperature control failed to toggle device | device_number=%s target=%s",
                device.device_number,
                next_state,
            )
            return

        if not gpio_service.sync_device_state_to_config(device_number=device.device_number):
            logger.error(
                "temperature control failed to sync config | device_number=%s",
                device.device_number,
            )

        actual_state = gpio_manager.read_is_on_by_number(device.device_number)
        device_dependency_service.handle_source_state_change(
            source_device_number=device.device_number
        )
        trigger_reason = (
            DeviceTriggerReason.TEMPERATURE_HYSTERESIS_ON
            if actual_state
            else DeviceTriggerReason.TEMPERATURE_HYSTERESIS_OFF
        )

        backend_adapter.log_device_event(
            device_uuid=device.device_uuid,
            device_id=device.device_id,
            device_number=device.device_number,
            event_type=DeviceEventType.STATE,
            is_on=actual_state,
            trigger_reason=trigger_reason,
            measured_value=snapshot.value,
            measured_unit=snapshot.unit,
        )
        await device_event_stream_service.publish_state_change(
            device=device,
            is_on=actual_state,
            event_type=DeviceEventType.STATE,
            trigger_reason=trigger_reason,
            measured_value=snapshot.value,
            measured_unit=snapshot.unit,
        )
        await heartbeat_service.publish_now(trigger=HeartbeatPublishTrigger.STATE_CHANGE)

        logger.info(
            "temperature hysteresis switch | device_number=%s sensor_id=%s temperature_c=%s state=%s",
            device.device_number,
            control.sensor_id,
            snapshot.value,
            actual_state,
        )

    async def _evaluate_scheduler_policy_device(
        self,
        *,
        device: RuntimeDevice,
        active_policy: ActiveSchedulerPolicy,
    ) -> None:
        policy = active_policy.policy
        snapshot = sensor_polling_service.get_latest_snapshot(policy.sensor_id)
        if snapshot is None or snapshot.status != SensorStatus.OK or snapshot.value is None:
            return

        current_is_on = gpio_manager.read_is_on_by_number(device.device_number)
        desired_state: bool | None = None
        next_phase = active_policy.phase

        if active_policy.phase == SchedulerTemperaturePhase.HEAT_UP:
            if snapshot.value >= policy.stop_threshold_c:
                desired_state = False
                next_phase = SchedulerTemperaturePhase.HOLD
            else:
                desired_state = True
        else:
            if current_is_on and snapshot.value >= policy.stop_threshold_c:
                desired_state = False
            elif (not current_is_on) and snapshot.value <= policy.start_threshold_c:
                desired_state = True

        if next_phase != active_policy.phase:
            self._active_scheduler_policies[device.device_number] = replace(
                active_policy,
                phase=next_phase,
            )

        if desired_state is None or desired_state == current_is_on:
            return

        desired_state = device_dependency_service.resolve_requested_state(
            device_number=device.device_number,
            requested_state=desired_state,
        )
        if desired_state == current_is_on:
            return

        changed = gpio_manager.set_state_by_number(device.device_number, desired_state)
        if not changed:
            logger.error(
                "scheduler policy failed to toggle device | device_number=%s target=%s",
                device.device_number,
                desired_state,
            )
            return

        gpio_service.sync_device_state_to_config(device_number=device.device_number)
        device_dependency_service.handle_source_state_change(
            source_device_number=device.device_number
        )
        await self._publish_scheduler_policy_event(
            device=device,
            trigger_reason=(
                DeviceTriggerReason.SCHEDULER_POLICY_HEAT_UP
                if desired_state
                else DeviceTriggerReason.SCHEDULER_POLICY_HOLD
            ),
            measured_value=snapshot.value,
            measured_unit=snapshot.unit,
        )


temperature_control_service = TemperatureControlService()

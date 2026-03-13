from __future__ import annotations

import asyncio
import logging

from app.core.device_event_stream_service import device_event_stream_service
from app.core.heartbeat_service import (
    HeartbeatPublishTrigger,
    heartbeat_service,
)
from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import DeviceMode
from app.domain.models.device_dependency import (
    DeviceDependencyAction,
    DeviceDependencyRule,
)
from app.infrastructure.backend.backend_adapter import (
    DeviceEventType,
    DeviceTriggerReason,
    backend_adapter,
)
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)


class DeviceDependencyService:
    def __init__(self) -> None:
        self._active_scheduler_rules: dict[int, DeviceDependencyRule] = {}

    @staticmethod
    def _schedule_or_run(coro) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return

        loop.create_task(coro)

    @staticmethod
    def _is_effective(rule: DeviceDependencyRule | None) -> bool:
        if rule is None:
            return False
        return (
            rule.when_source_on != DeviceDependencyAction.NONE
            or rule.when_source_off != DeviceDependencyAction.NONE
        )

    def set_scheduler_rule(
        self,
        *,
        source_device_number: int,
        rule: DeviceDependencyRule | None,
    ) -> None:
        if not self._is_effective(rule):
            self._active_scheduler_rules.pop(source_device_number, None)
            return
        self._active_scheduler_rules[source_device_number] = rule

    def clear_scheduler_rule(self, *, source_device_number: int) -> DeviceDependencyRule | None:
        return self._active_scheduler_rules.pop(source_device_number, None)

    def resolve_requested_state(
        self,
        *,
        device_number: int,
        requested_state: bool,
    ) -> bool:
        forced_state = self._resolve_forced_state(target_device_number=device_number)
        if forced_state is None:
            return requested_state
        return forced_state

    def _active_rule_for_source(
        self,
        source_device: RuntimeDevice,
    ) -> DeviceDependencyRule | None:
        if source_device.mode == DeviceMode.SCHEDULE:
            scheduler_rule = self._active_scheduler_rules.get(source_device.device_number)
            if self._is_effective(scheduler_rule):
                return scheduler_rule

        if source_device.mode == DeviceMode.AUTO and self._is_effective(
            source_device.device_dependency_rule
        ):
            return source_device.device_dependency_rule

        return None

    @staticmethod
    def _rule_state_for_source(
        *,
        source_is_on: bool,
        rule: DeviceDependencyRule,
    ) -> bool | None:
        action = rule.when_source_on if source_is_on else rule.when_source_off
        if action == DeviceDependencyAction.ON:
            return True
        if action == DeviceDependencyAction.OFF:
            return False
        return None

    def _resolve_forced_state(self, *, target_device_number: int) -> bool | None:
        for source_device in gpio_manager.devices_by_number.values():
            rule = self._active_rule_for_source(source_device)
            if rule is None or rule.target_device_number != target_device_number:
                continue

            source_is_on = gpio_manager.read_is_on_by_number(source_device.device_number)
            return self._rule_state_for_source(
                source_is_on=source_is_on,
                rule=rule,
            )

        return None

    def reconcile_target(self, *, target_device_number: int) -> bool:
        target_device = gpio_manager.get_by_number(target_device_number)
        if target_device is None:
            logger.warning(
                "dependency target not found | target_device_number=%s",
                target_device_number,
            )
            return False

        forced_state = self._resolve_forced_state(target_device_number=target_device_number)
        desired_state = forced_state
        if desired_state is None and target_device.mode == DeviceMode.MANUAL:
            desired_state = target_device.desired_state
        if desired_state is None:
            return False

        current_state = gpio_manager.read_is_on_by_number(target_device_number)
        if current_state == desired_state:
            return False

        changed = gpio_manager.set_runtime_override_by_number(
            target_device_number,
            desired_state,
        )
        if not changed:
            logger.error(
                "dependency failed to set target state | target_device_number=%s state=%s",
                target_device_number,
                desired_state,
            )
            return False

        self._publish_dependency_state_change(
            target_device=target_device,
            is_on=desired_state,
        )
        return True

    def handle_source_state_change(self, *, source_device_number: int) -> bool:
        source_device = gpio_manager.get_by_number(source_device_number)
        if source_device is None:
            return False

        rule = self._active_rule_for_source(source_device)
        if rule is None:
            return False
        return self.reconcile_target(target_device_number=rule.target_device_number)

    def reconcile_all(self) -> None:
        target_numbers = {
            rule.target_device_number
            for rule in self._active_scheduler_rules.values()
            if self._is_effective(rule)
        }
        target_numbers.update(
            source_device.device_dependency_rule.target_device_number
            for source_device in gpio_manager.devices_by_number.values()
            if source_device.mode == DeviceMode.AUTO
            and self._is_effective(source_device.device_dependency_rule)
            and source_device.device_dependency_rule is not None
        )

        for target_device_number in sorted(target_numbers):
            self.reconcile_target(target_device_number=target_device_number)

    @staticmethod
    def _publish_dependency_state_change(
        *,
        target_device: RuntimeDevice,
        is_on: bool,
    ) -> None:
        trigger_reason = (
            DeviceTriggerReason.DEVICE_DEPENDENCY_ON
            if is_on
            else DeviceTriggerReason.DEVICE_DEPENDENCY_OFF
        )

        backend_adapter.log_device_event(
            device_uuid=target_device.device_uuid,
            device_id=target_device.device_id,
            device_number=target_device.device_number,
            event_type=DeviceEventType.STATE,
            is_on=is_on,
            trigger_reason=trigger_reason,
        )

        DeviceDependencyService._schedule_or_run(
            device_event_stream_service.publish_state_change(
                device=target_device,
                is_on=is_on,
                event_type=DeviceEventType.STATE,
                trigger_reason=trigger_reason,
            )
        )
        DeviceDependencyService._schedule_or_run(
            heartbeat_service.publish_now(
                trigger=HeartbeatPublishTrigger.STATE_CHANGE,
            )
        )


device_dependency_service = DeviceDependencyService()

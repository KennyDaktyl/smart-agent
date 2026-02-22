from typing import List

from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import AgentConfig
from app.domain.models.hardware_config import HardwareConfig


def merge_configs(
    agent_config: AgentConfig,
    hardware_config: HardwareConfig,
) -> List[RuntimeDevice]:

    configured_count = len(agent_config.devices)
    if configured_count > agent_config.device_max:
        raise RuntimeError(
            f"Configured devices ({configured_count}) exceed device_max "
            f"({agent_config.device_max})"
        )

    merged: List[RuntimeDevice] = []
    seen_device_ids: set[int] = set()
    seen_device_uuids: set[str] = set()

    for device_number in sorted(agent_config.devices):
        domain_device = agent_config.devices[device_number]
        hw = hardware_config.devices.get(device_number)

        if domain_device.device_number != device_number:
            raise RuntimeError(
                "Device mapping mismatch: key "
                f"{device_number} != payload {domain_device.device_number}"
            )

        if hw is None:
            raise RuntimeError(
                f"Device number {device_number} missing in hardware config"
            )

        if domain_device.device_id in seen_device_ids:
            raise RuntimeError(
                f"Duplicate device_id detected: {domain_device.device_id}"
            )
        seen_device_ids.add(domain_device.device_id)

        if domain_device.device_uuid in seen_device_uuids:
            raise RuntimeError(
                f"Duplicate device_uuid detected: {domain_device.device_uuid}"
            )
        seen_device_uuids.add(domain_device.device_uuid)

        merged.append(
            RuntimeDevice(
                device_id=domain_device.device_id,
                device_uuid=domain_device.device_uuid,
                device_number=domain_device.device_number,
                gpio=hw.gpio,
                active_low=hw.active_low,
                mode=domain_device.mode,
                threshold_value=domain_device.threshold_value,
                rated_power=domain_device.rated_power,
                desired_state=domain_device.desired_state,
            )
        )

    return merged

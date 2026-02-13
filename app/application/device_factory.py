from typing import List

from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import AgentConfig
from app.domain.models.hardware_config import HardwareConfig


def merge_configs(
    agent_config: AgentConfig,
    hardware_config: HardwareConfig,
) -> List[RuntimeDevice]:

    merged = []

    for device_number, domain_device in agent_config.devices.items():
        hw = hardware_config.devices.get(device_number)

        if not hw:
            raise RuntimeError(
                f"Device number {device_number} missing in hardware config"
            )

        merged.append(
            RuntimeDevice(
                device_number=device_number,
                device_id=domain_device.device_id,
                gpio=hw.gpio,
                active_low=hw.active_low,
                mode=domain_device.mode,
                power_threshold=domain_device.power_threshold,
                rated_power=domain_device.rated_power,
                desired_state=domain_device.desired_state,
            )
        )

    return merged

from dataclasses import dataclass


@dataclass
class RuntimeDevice:
    device_number: int
    device_id: int
    gpio: int
    active_low: bool
    mode: str
    rated_power: float
    power_threshold: float | None = None
    desired_state: bool = False

from enum import Enum


class DeviceMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO_POWER = "AUTO_POWER"
    SCHEDULE = "SCHEDULE"

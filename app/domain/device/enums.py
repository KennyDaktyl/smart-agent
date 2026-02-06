from enum import Enum


class DeviceMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    SCHEDULE = "SCHEDULE"

# app/domain/gpio/enums.py

from enum import Enum


class GPIODirection(str, Enum):
    OUT = "OUT"
    IN = "IN"


class GPIOState(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"

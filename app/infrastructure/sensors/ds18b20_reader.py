from __future__ import annotations

from pathlib import Path


DEFAULT_DS18B20_ROOT = Path("/sys/bus/w1/devices")


def parse_ds18b20_temperature_c(
    raw_contents: str,
    *,
    offset_c: float = 0.0,
) -> float:
    lines = [line.strip() for line in raw_contents.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("Incomplete DS18B20 payload")
    if not lines[0].endswith("YES"):
        raise ValueError("DS18B20 CRC validation failed")

    marker = "t="
    position = lines[1].find(marker)
    if position < 0:
        raise ValueError("DS18B20 payload missing temperature marker")

    milli_c = int(lines[1][position + len(marker) :])
    return round((milli_c / 1000.0) + offset_c, 2)


def read_ds18b20_temperature_c(
    *,
    address: str,
    offset_c: float = 0.0,
    devices_root: Path = DEFAULT_DS18B20_ROOT,
) -> float:
    slave_path = devices_root / address / "w1_slave"
    raw_contents = slave_path.read_text(encoding="utf-8")
    return parse_ds18b20_temperature_c(raw_contents, offset_c=offset_c)

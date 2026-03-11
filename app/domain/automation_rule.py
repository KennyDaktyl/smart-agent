from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

BATTERY_SOC_UNIT = "%"
POWER_RULE_UNITS = frozenset({"W", "kW", "MW"})


class AutomationRuleGroupOperator(str, Enum):
    ALL = "ALL"
    ANY = "ANY"


class AutomationRuleComparator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class AutomationRuleSource(str, Enum):
    PROVIDER_PRIMARY_POWER = "provider_primary_power"
    PROVIDER_BATTERY_SOC = "provider_battery_soc"


class AutomationRuleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: AutomationRuleSource
    comparator: AutomationRuleComparator = AutomationRuleComparator.GTE
    value: float = Field(..., ge=0)
    unit: str

    @model_validator(mode="after")
    def validate_for_source(self):
        if self.source == AutomationRuleSource.PROVIDER_BATTERY_SOC:
            if self.unit != BATTERY_SOC_UNIT:
                raise ValueError("provider_battery_soc conditions must use % unit")
            if self.value > 100:
                raise ValueError("provider_battery_soc value must be between 0 and 100")
            return self

        if self.source == AutomationRuleSource.PROVIDER_PRIMARY_POWER:
            if self.unit not in POWER_RULE_UNITS:
                raise ValueError(
                    "provider_primary_power unit must be one of: "
                    f"{', '.join(sorted(POWER_RULE_UNITS))}"
                )
            return self

        raise ValueError(f"unsupported automation rule source: {self.source}")


class AutomationRuleGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: AutomationRuleGroupOperator = AutomationRuleGroupOperator.ANY
    items: list[AutomationRuleCondition | AutomationRuleGroup] | None = Field(
        default=None
    )
    conditions: list[AutomationRuleCondition] | None = Field(
        default=None,
        exclude=True,
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_conditions(cls, value: object):
        if not isinstance(value, Mapping):
            return value

        data = dict(value)
        if data.get("items") is None and data.get("conditions") is not None:
            data["items"] = data.get("conditions")
        return data

    @model_validator(mode="after")
    def validate_items(self):
        if self.items is None and self.conditions is None:
            raise ValueError("automation rule group requires items or conditions")

        if self.items is not None and self.conditions is not None:
            if len(self.items) != len(self.conditions):
                raise ValueError(
                    "automation rule group cannot define both items and conditions"
                )

        if self.items is None:
            self.items = list(self.conditions or [])

        if not self.items:
            raise ValueError("automation rule group must contain at least one item")

        self.conditions = None
        return self


AutomationRuleGroup.model_rebuild()


@dataclass(frozen=True)
class MetricSnapshot:
    value: float
    unit: str | None = None


def build_legacy_power_rule(
    *,
    value: float,
    unit: str,
    comparator: AutomationRuleComparator = AutomationRuleComparator.GTE,
) -> AutomationRuleGroup:
    return AutomationRuleGroup(
        operator=AutomationRuleGroupOperator.ANY,
        items=[
            AutomationRuleCondition(
                source=AutomationRuleSource.PROVIDER_PRIMARY_POWER,
                comparator=comparator,
                value=value,
                unit=unit,
            )
        ],
    )


def extract_legacy_power_threshold(
    rule: AutomationRuleGroup | None,
) -> tuple[float, str] | None:
    if rule is None or rule.operator != AutomationRuleGroupOperator.ANY:
        return None

    items = rule.items or []
    if len(items) != 1:
        return None

    condition = items[0]
    if not isinstance(condition, AutomationRuleCondition):
        return None
    if condition.source != AutomationRuleSource.PROVIDER_PRIMARY_POWER:
        return None
    if condition.comparator != AutomationRuleComparator.GTE:
        return None

    return condition.value, condition.unit


def iter_conditions(
    rule: AutomationRuleGroup | None,
) -> Iterable[AutomationRuleCondition]:
    if rule is None:
        return []
    return list(_iter_nodes(rule))


def uses_source(
    rule: AutomationRuleGroup | None,
    source: AutomationRuleSource,
) -> bool:
    if rule is None:
        return False
    return any(condition.source == source for condition in _iter_nodes(rule))


def evaluate_rule(
    rule: AutomationRuleGroup,
    measurements: Mapping[AutomationRuleSource, MetricSnapshot | None],
) -> bool:
    return _evaluate_group(rule, measurements)


def _evaluate_group(
    group: AutomationRuleGroup,
    measurements: Mapping[AutomationRuleSource, MetricSnapshot | None],
) -> bool:
    results = [_evaluate_item(item, measurements) for item in group.items or []]
    if group.operator == AutomationRuleGroupOperator.ALL:
        return all(results)
    return any(results)


def _evaluate_item(
    item: AutomationRuleCondition | AutomationRuleGroup,
    measurements: Mapping[AutomationRuleSource, MetricSnapshot | None],
) -> bool:
    if isinstance(item, AutomationRuleCondition):
        return _evaluate_condition(item, measurements)
    return _evaluate_group(item, measurements)


def _evaluate_condition(
    condition: AutomationRuleCondition,
    measurements: Mapping[AutomationRuleSource, MetricSnapshot | None],
) -> bool:
    metric = measurements.get(condition.source)
    if metric is None:
        return False

    measured_value = _normalize_metric_value(metric=metric, condition=condition)
    if measured_value is None:
        return False

    return _compare_values(
        measured_value=measured_value,
        threshold_value=condition.value,
        comparator=condition.comparator,
    )


def _normalize_metric_value(
    *,
    metric: MetricSnapshot,
    condition: AutomationRuleCondition,
) -> float | None:
    if condition.source == AutomationRuleSource.PROVIDER_BATTERY_SOC:
        metric_unit = (metric.unit or BATTERY_SOC_UNIT).strip()
        if metric_unit != BATTERY_SOC_UNIT:
            return None
        return metric.value

    if condition.source == AutomationRuleSource.PROVIDER_PRIMARY_POWER:
        metric_unit = _normalize_power_unit(metric.unit)
        condition_unit = _normalize_power_unit(condition.unit)
        if metric_unit is None or condition_unit is None:
            return None
        return _convert_power(metric.value, from_unit=metric_unit, to_unit=condition_unit)

    return None


def _normalize_power_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    normalized = unit.strip()
    if normalized in POWER_RULE_UNITS:
        return normalized
    return None


def _convert_power(value: float, *, from_unit: str, to_unit: str) -> float:
    factors = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0}
    watts = value * factors[from_unit]
    return watts / factors[to_unit]


def _compare_values(
    *,
    measured_value: float,
    threshold_value: float,
    comparator: AutomationRuleComparator,
) -> bool:
    if comparator == AutomationRuleComparator.GT:
        return measured_value > threshold_value
    if comparator == AutomationRuleComparator.GTE:
        return measured_value >= threshold_value
    if comparator == AutomationRuleComparator.LT:
        return measured_value < threshold_value
    if comparator == AutomationRuleComparator.LTE:
        return measured_value <= threshold_value
    return False


def _iter_nodes(
    rule: AutomationRuleGroup,
) -> Iterable[AutomationRuleCondition]:
    for item in rule.items or []:
        if isinstance(item, AutomationRuleCondition):
            yield item
            continue
        yield from _iter_nodes(item)

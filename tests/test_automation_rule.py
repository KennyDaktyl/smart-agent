import unittest

from app.domain.automation_rule import (
    AutomationRuleComparator,
    AutomationRuleCondition,
    AutomationRuleGroup,
    AutomationRuleGroupOperator,
    AutomationRuleSource,
    MetricSnapshot,
    evaluate_rule,
    find_first_matching_condition,
)


class AutomationRuleEvaluationTests(unittest.TestCase):
    def test_nested_groups_support_mixed_or_and_logic(self):
        rule = AutomationRuleGroup(
            operator=AutomationRuleGroupOperator.ALL,
            items=[
                AutomationRuleGroup(
                    operator=AutomationRuleGroupOperator.ANY,
                    items=[
                        AutomationRuleCondition(
                            source=AutomationRuleSource.PROVIDER_PRIMARY_POWER,
                            comparator=AutomationRuleComparator.GTE,
                            value=2.0,
                            unit="kW",
                        ),
                        AutomationRuleCondition(
                            source=AutomationRuleSource.PROVIDER_BATTERY_SOC,
                            comparator=AutomationRuleComparator.GTE,
                            value=30.0,
                            unit="%",
                        ),
                    ],
                ),
                AutomationRuleCondition(
                    source=AutomationRuleSource.PROVIDER_PRIMARY_POWER,
                    comparator=AutomationRuleComparator.LTE,
                    value=5.0,
                    unit="kW",
                ),
            ],
        )

        measurements = {
            AutomationRuleSource.PROVIDER_PRIMARY_POWER: MetricSnapshot(
                value=4.0,
                unit="kW",
            ),
            AutomationRuleSource.PROVIDER_BATTERY_SOC: MetricSnapshot(
                value=20.0,
                unit="%",
            ),
        }

        self.assertTrue(evaluate_rule(rule, measurements))

    def test_find_first_matching_condition_prefers_first_satisfied_item(self):
        rule = AutomationRuleGroup(
            operator=AutomationRuleGroupOperator.ANY,
            items=[
                AutomationRuleCondition(
                    source=AutomationRuleSource.PROVIDER_BATTERY_SOC,
                    comparator=AutomationRuleComparator.GTE,
                    value=50.0,
                    unit="%",
                ),
                AutomationRuleCondition(
                    source=AutomationRuleSource.PROVIDER_PRIMARY_POWER,
                    comparator=AutomationRuleComparator.GTE,
                    value=100.0,
                    unit="W",
                ),
            ],
        )

        measurements = {
            AutomationRuleSource.PROVIDER_PRIMARY_POWER: MetricSnapshot(
                value=207.12,
                unit="W",
            ),
            AutomationRuleSource.PROVIDER_BATTERY_SOC: MetricSnapshot(
                value=95.0,
                unit="%",
            ),
        }

        match = find_first_matching_condition(rule, measurements)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.condition.source, AutomationRuleSource.PROVIDER_BATTERY_SOC)
        self.assertEqual(match.measured_value, 95.0)
        self.assertEqual(match.measured_unit, "%")


if __name__ == "__main__":
    unittest.main()

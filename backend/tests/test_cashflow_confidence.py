"""Cashflow Confidence tests — spec §6.7, testing prompt §18."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import Category, Direction
from app.services import cashflow_confidence as cc
from conftest import txn


def _statement(
    months=6,
    income=Decimal("3200"),
    income_day=28,
    essential=Decimal("1450"),
    discretionary=Decimal("400"),
    income_jitter=Decimal("0"),
    spend_jitter=Decimal("0"),
):
    """Build a synthetic statement with controllable regularity."""
    rows = []
    for m in range(1, months + 1):
        drift = income_jitter * Decimal(m % 3)
        rows.append(
            txn(date(2026, m, income_day), "ACME PAYROLL", income + drift,
                direction=Direction.CREDIT, category=Category.SALARY_INCOME,
                merchant="Acme Payroll")
        )
        rows.append(
            txn(date(2026, m, 3), "GREENFIELD RENT", essential,
                category=Category.RENT_HOUSING, merchant="Greenfield")
        )
        rows.append(
            txn(date(2026, m, 12), "SHOPPING", discretionary + spend_jitter * Decimal(m % 4),
                category=Category.SHOPPING, merchant="Shop")
        )
    return rows


# --- score bounds and shape -------------------------------------------------


def test_score_between_0_and_100():
    result = cc.compute(_statement(), latest_balance=Decimal("4000"))
    assert 0 <= result.score <= 100


def test_all_four_components_present_with_correct_weights():
    result = cc.compute(_statement(), latest_balance=Decimal("4000"))
    names = {c.name for c in result.components}
    assert names == {
        "income_regularity",
        "essential_predictability",
        "buffer_coverage",
        "spending_stability",
    }
    weights = {c.name: c.weight for c in result.components}
    assert weights["income_regularity"] == 0.30
    assert weights["essential_predictability"] == 0.25
    assert weights["buffer_coverage"] == 0.30
    assert weights["spending_stability"] == 0.15
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_score_equals_sum_of_component_points():
    result = cc.compute(_statement(), latest_balance=Decimal("4000"))
    assert result.score == int(round(sum(c.points for c in result.components)))


def test_every_component_is_explainable():
    """§6.7 requires evidence for each component."""
    result = cc.compute(_statement(), latest_balance=Decimal("4000"))
    for component in result.components:
        assert component.explanation
        assert 0.0 <= component.value <= 1.0


# --- component behaviour ----------------------------------------------------


def test_stable_salary_scores_higher_than_irregular_salary():
    stable = cc.compute(_statement(), latest_balance=Decimal("4000"))
    irregular = cc.compute(
        _statement(income_jitter=Decimal("900")), latest_balance=Decimal("4000")
    )
    a = next(c for c in stable.components if c.name == "income_regularity")
    b = next(c for c in irregular.components if c.name == "income_regularity")
    assert a.value > b.value


def test_missing_salary_marks_income_component_unavailable():
    rows = [
        txn(date(2026, m, 3), "GREENFIELD RENT", "1450",
            category=Category.RENT_HOUSING, merchant="Greenfield")
        for m in range(1, 5)
    ]
    result = cc.compute(rows, latest_balance=Decimal("1000"))
    income = next(c for c in result.components if c.name == "income_regularity")
    assert income.available is False
    assert income.points == 0.0
    assert "income_regularity_unavailable" in result.missing_inputs


def test_strong_buffer_scores_higher_than_weak_buffer():
    strong = cc.compute(_statement(), latest_balance=Decimal("6000"))
    weak = cc.compute(_statement(), latest_balance=Decimal("200"))
    a = next(c for c in strong.components if c.name == "buffer_coverage")
    b = next(c for c in weak.components if c.name == "buffer_coverage")
    assert a.value > b.value
    assert strong.score > weak.score


def test_buffer_caps_at_full_coverage():
    """A very large balance cannot push the component above 1.0."""
    result = cc.compute(_statement(), latest_balance=Decimal("500000"))
    buffer = next(c for c in result.components if c.name == "buffer_coverage")
    assert buffer.value == 1.0


def test_estimated_balance_is_discounted():
    verified = cc.compute(_statement(), latest_balance=Decimal("4000"))
    estimated = cc.compute(
        _statement(), latest_balance=Decimal("4000"), balance_is_estimated=True
    )
    a = next(c for c in verified.components if c.name == "buffer_coverage")
    b = next(c for c in estimated.components if c.name == "buffer_coverage")
    assert b.value < a.value
    assert estimated.confidence < verified.confidence


def test_volatile_spending_scores_lower_than_stable_spending():
    stable = cc.compute(_statement(), latest_balance=Decimal("4000"))
    volatile = cc.compute(
        _statement(spend_jitter=Decimal("1200")), latest_balance=Decimal("4000")
    )
    a = next(c for c in stable.components if c.name == "spending_stability")
    b = next(c for c in volatile.components if c.name == "spending_stability")
    assert a.value > b.value


# --- missing data reduces confidence, never invents values ------------------


def test_missing_balance_lowers_confidence_and_does_not_invent_a_buffer():
    result = cc.compute(_statement(), latest_balance=None)
    buffer = next(c for c in result.components if c.name == "buffer_coverage")
    assert buffer.available is False
    assert buffer.value == 0.0
    assert result.confidence < 1.0
    assert "no balance" in buffer.explanation.lower()


def test_empty_statement_returns_unknown_not_a_fabricated_score():
    result = cc.compute([])
    assert result.score == 0
    assert result.band == "unknown"
    assert "no_transactions" in result.missing_inputs
    assert result.improvement_suggestions


def test_thin_history_lowers_confidence():
    thin = cc.compute(_statement(months=1), latest_balance=Decimal("4000"))
    thick = cc.compute(_statement(months=6), latest_balance=Decimal("4000"))
    assert thin.confidence < thick.confidence
    assert "less_than_two_months_of_history" in thin.missing_inputs


# --- §6.7 prohibitions ------------------------------------------------------


def test_never_described_as_a_credit_score():
    result = cc.compute(_statement(), latest_balance=Decimal("4000"))
    assert "not a credit score" in result.disclaimer.lower()
    blob = " ".join(
        [result.disclaimer, result.band]
        + [c.explanation for c in result.components]
        + result.improvement_suggestions
    ).lower()
    for forbidden in ("creditworthy", "creditworthiness", "credit rating", "fico"):
        assert forbidden not in blob


def test_uses_no_sensitive_personal_attributes():
    """The scorer only ever sees transactions; assert its inputs stay that way."""
    import inspect

    source = inspect.getsource(cc)
    for attribute in ("age", "gender", "race", "ethnic", "religion", "marital", "postcode"):
        assert attribute not in source.lower()


def test_score_is_deterministic():
    a = cc.compute(_statement(), latest_balance=Decimal("4000"))
    b = cc.compute(_statement(), latest_balance=Decimal("4000"))
    assert a.score == b.score
    assert [c.points for c in a.components] == [c.points for c in b.components]


def test_improvement_suggestions_are_actionable_and_bounded():
    result = cc.compute(_statement(months=2), latest_balance=Decimal("50"))
    assert result.improvement_suggestions
    assert len(result.improvement_suggestions) <= 3

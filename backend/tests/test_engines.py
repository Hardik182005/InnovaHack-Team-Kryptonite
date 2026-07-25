"""Unit tests for the deterministic engines (spec §24 unit-test list)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import Category, Direction, Essentiality, Frequency, ReviewStatus
from app.services import categorization, merchant_normalization as mn
from app.services import price_changes, projections, recurrence, roundups, safe_spare
from conftest import txn


# --- round-up arithmetic ----------------------------------------------------


@pytest.mark.parametrize(
    "amount,increment,expected",
    [
        ("4.30", "1.00", "0.70"),
        ("10.00", "1.00", "0.00"),   # exact multiple -> no spare change
        ("10.01", "5.00", "4.99"),
        ("0.01", "1.00", "0.99"),
        ("99.99", "10.00", "0.01"),
        ("7.50", "2.50", "0.00"),
    ],
)
def test_round_up_formula(amount, increment, expected):
    assert roundups.round_up_for_amount(
        Decimal(amount), Decimal(increment)
    ) == Decimal(expected)


def test_round_up_rejects_non_positive_increment():
    with pytest.raises(ValueError):
        roundups.RoundUpRules(increment=Decimal("0"))


def test_paused_roundups_contribute_nothing():
    rows = [txn(0, "CAFE", "4.30", category=Category.DINING_DELIVERY)]
    r = roundups.calculate_roundups(rows, rules=roundups.RoundUpRules(paused=True))
    assert r.allowed_round_up_total == Decimal("0.00")
    assert r.limiting_factor == "paused"
    assert "paused" in r.explanation.lower()


def test_zero_roundups_are_always_explained():
    """§6.8: when the allowed amount is zero, explain why."""
    rows = [txn(0, "RENT", "1500.00", category=Category.RENT_HOUSING)]
    r = roundups.calculate_roundups(rows)
    assert r.allowed_round_up_total == Decimal("0.00")
    assert r.explanation


def test_excluded_merchant_is_skipped():
    rows = [txn(0, "Peak Fitness", "49.10", category=Category.FITNESS, merchant="Peak Fitness")]
    r = roundups.calculate_roundups(
        rows, rules=roundups.RoundUpRules(excluded_merchants=frozenset({"peak fitness"}))
    )
    assert r.eligible_count == 0
    assert r.lines[0].reason == "excluded_merchant"


def test_large_uncertain_transaction_excluded():
    rows = [txn(0, "CAR DEALER", "9500.40", category=Category.SHOPPING)]
    r = roundups.calculate_roundups(rows)
    assert r.lines[0].reason == "large_uncertain_transaction"


# --- transaction model ------------------------------------------------------


def test_signed_amount_is_normalised_to_direction():
    """A negative debit import becomes a positive credit, not a negative debit."""
    t = txn(0, "REFUND", "-25.00", direction=Direction.DEBIT)
    assert t.amount == Decimal("25.00")
    assert t.direction is Direction.CREDIT


def test_money_uses_decimal_not_float():
    t = txn(0, "X", 0.1 + 0.2)  # 0.30000000000000004 as a float
    assert t.amount == Decimal("0.30")


# --- merchant normalization (§9) -------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["NETFLIX.COM", "NETFLIX INDIA", "NFX*SUBSCRIPTION", "POS NETFLIX 12/04 XXXX1234"],
)
def test_netflix_variants_resolve_together(raw):
    """The spec's own §9 example."""
    assert mn.resolve_merchant(raw).normalized_merchant == "Netflix"


def test_resolution_records_method_and_confidence():
    res = mn.resolve_merchant("NETFLIX.COM")
    assert res.method in ("exact_alias", "regex_alias")
    assert res.confidence >= 0.95


def test_unknown_merchant_gets_low_confidence_for_review():
    res = mn.resolve_merchant("ZZQQ TRADING 99")
    assert res.confidence < 0.7  # routed to review, kept out of round-ups


def test_batch_groups_repeat_unknown_merchants():
    out = mn.normalize_all(["QUIRKY BEANS CO", "QUIRKY BEANS CO 123", "QUIRKY BEANS"])
    assert len({r.normalized_merchant for r in out}) == 1


def test_longest_alias_wins():
    assert mn.resolve_merchant("AMAZON PRIME MEMBER").normalized_merchant == "Amazon Prime"


# --- categorization (§10) ---------------------------------------------------


@pytest.mark.parametrize(
    "description,expected",
    [
        ("ACME PAYROLL DIRECT DEPOSIT", Category.SALARY_INCOME),
        ("GREENFIELD PROPERTIES RENT", Category.RENT_HOUSING),
        ("SECURELIFE INSURANCE PREMIUM", Category.INSURANCE),
        ("CITY POWER ELECTRIC BILL", Category.UTILITIES),
        ("MERCY CLINIC", Category.MEDICAL),
        ("ATM CASH WITHDRAWAL", Category.CASH_WITHDRAWAL),
        ("FIRSTBANK AUTO LOAN EMI", Category.LOAN_EMI),
    ],
)
def test_keyword_classification(description, expected):
    direction = (
        Direction.CREDIT if expected is Category.SALARY_INCOME else Direction.DEBIT
    )
    assert classify_cat(description, direction) is expected


def classify_cat(description, direction=Direction.DEBIT):
    return categorization.classify(description, direction=direction).category


def test_essential_categories_marked_essential():
    result = categorization.classify("GREENFIELD PROPERTIES RENT")
    assert result.essentiality is Essentiality.ESSENTIAL


def test_unresolved_transaction_is_low_confidence_and_unknown():
    result = categorization.classify("QX7 99231")
    assert result.category is Category.UNKNOWN
    assert result.confidence < 0.5
    assert result.essentiality is Essentiality.UNKNOWN


def test_user_override_is_not_reclassified():
    t = txn(0, "GREENFIELD RENT", "1500", category=Category.SHOPPING)
    t.user_overridden = True
    categorization.classify_transactions([t])
    assert t.category is Category.SHOPPING  # untouched


def test_category_breakdown_percentages():
    rows = categorization.classify_transactions(
        [
            txn(0, "CORNER SUPERMARKET", "300"),
            txn(1, "PIZZA PLACE", "100"),
        ]
    )
    breakdown = categorization.category_breakdown(rows)
    assert breakdown[Category.GROCERIES]["percentage"] == 75.0
    assert breakdown[Category.DINING_DELIVERY]["percentage"] == 25.0


# --- recurrence (§11) -------------------------------------------------------


def test_monthly_subscription_detected_and_confirmed():
    rows = [
        txn(date(2026, m, 14), "Netflix", "15.99",
            category=Category.SUBSCRIPTION, merchant="Netflix")
        for m in range(1, 7)
    ]
    patterns = recurrence.detect_recurring(rows)
    assert len(patterns) == 1
    p = patterns[0]
    assert p.frequency is Frequency.MONTHLY
    assert p.occurrences == 6
    assert p.status is ReviewStatus.CONFIRMED
    assert p.confidence >= 90
    assert p.median_amount == Decimal("15.99")


def test_annual_renewal_detected_from_two_charges():
    rows = [
        txn(date(2025, 3, 2), "Domain Host", "72.00",
            category=Category.SOFTWARE, merchant="Domain Host"),
        txn(date(2026, 3, 1), "Domain Host", "72.00",
            category=Category.SOFTWARE, merchant="Domain Host"),
    ]
    patterns = recurrence.detect_recurring(rows)
    assert patterns and patterns[0].frequency is Frequency.ANNUAL


def test_utilities_tolerate_variable_amounts():
    """A bill that swings 20% must still be recognised as recurring."""
    amounts = ["88.00", "104.00", "79.00", "96.00", "112.00", "85.00"]
    rows = [
        txn(date(2026, m, 9), "City Power", amounts[m - 1],
            category=Category.UTILITIES, merchant="City Power")
        for m in range(1, 7)
    ]
    patterns = recurrence.detect_recurring(rows)
    assert patterns[0].status in (ReviewStatus.CONFIRMED, ReviewStatus.LIKELY)
    assert patterns[0].amount_varies is True


def test_random_one_off_purchases_are_not_recurring():
    rows = [
        txn(date(2026, 1, 3), "Shop A", "20"),
        txn(date(2026, 1, 9), "Shop B", "35"),
        txn(date(2026, 2, 17), "Shop C", "12"),
    ]
    assert recurrence.detect_recurring(rows) == []


def test_monthly_equivalent_normalises_cadence():
    rows = [
        txn(date(2025, 3, 2), "Domain Host", "120.00",
            category=Category.SOFTWARE, merchant="Domain Host"),
        txn(date(2026, 3, 1), "Domain Host", "120.00",
            category=Category.SOFTWARE, merchant="Domain Host"),
    ]
    p = recurrence.detect_recurring(rows)[0]
    assert Decimal("9.00") < p.monthly_equivalent < Decimal("11.00")


# --- Safe Spare (§6.6) ------------------------------------------------------


def test_volatility_reserve_grows_with_instability():
    steady = safe_spare.SafeSpareInputs(
        latest_verified_balance=Decimal("3000"),
        recent_monthly_outflows=[Decimal("1000")] * 4,
        average_monthly_essential_spending=Decimal("800"),
    )
    erratic = safe_spare.SafeSpareInputs(
        latest_verified_balance=Decimal("3000"),
        recent_monthly_outflows=[Decimal("400"), Decimal("2200"), Decimal("700"), Decimal("1900")],
        average_monthly_essential_spending=Decimal("800"),
    )
    a = safe_spare.compute_safe_spare(steady)
    b = safe_spare.compute_safe_spare(erratic)
    assert a.volatility_reserve == Decimal("0.00")
    assert b.volatility_reserve > 0
    assert b.safe_spare_now < a.safe_spare_now


def test_buffer_is_max_of_minimum_and_percentage():
    inputs = safe_spare.SafeSpareInputs(
        latest_verified_balance=Decimal("5000"),
        average_monthly_essential_spending=Decimal("2000"),
    )
    settings = safe_spare.SafeSpareSettings(
        user_minimum_buffer=Decimal("200"), buffer_percentage=Decimal("0.25")
    )
    # 25% of 2000 = 500 > 200 minimum
    assert safe_spare.compute_safe_spare(inputs, settings).safety_buffer == Decimal("500.00")


def test_user_monthly_cap_limits_contribution():
    inputs = safe_spare.SafeSpareInputs(
        latest_verified_balance=Decimal("5000"),
        calculated_monthly_surplus=Decimal("900"),
        average_monthly_essential_spending=Decimal("100"),
    )
    settings = safe_spare.SafeSpareSettings(user_monthly_cap=Decimal("50"))
    result = safe_spare.compute_safe_spare(inputs, settings)
    assert result.safe_monthly_contribution == Decimal("50.00")
    assert result.limiting_factor == "user_monthly_cap"
    assert "cap you set" in result.reason


def test_build_inputs_derives_income_cadence(salary_and_rent):
    inputs = safe_spare.build_inputs(salary_and_rent)
    assert inputs.next_income_date is not None
    assert inputs.average_monthly_essential_spending > 0
    assert inputs.calculated_monthly_surplus > 0


def test_build_inputs_handles_empty_statement():
    inputs = safe_spare.build_inputs([])
    assert inputs.missing_inputs == ["no_transactions"]
    assert safe_spare.compute_safe_spare(inputs).safe_spare_now == Decimal("0.00")


# --- projections (§6.10) ----------------------------------------------------


def test_future_value_matches_annuity_formula():
    # 100/mo at 12% nominal (1%/mo) for 12 months, no principal.
    fv = projections.future_value(Decimal("0"), Decimal("100"), Decimal("0.01"), 12)
    assert Decimal("1268.00") < fv < Decimal("1269.00")


def test_future_value_zero_months_returns_principal():
    assert projections.future_value(Decimal("500"), Decimal("100"), Decimal("0.01"), 0) == Decimal("500.00")


def test_required_contribution_zero_rate():
    req = projections.required_monthly_contribution(
        Decimal("1200"), Decimal("0"), Decimal("0"), 12
    )
    assert req == Decimal("100.00")


def test_required_contribution_zero_when_principal_already_suffices():
    req = projections.required_monthly_contribution(
        Decimal("100"), Decimal("5000"), Decimal("0.01"), 12
    )
    assert req == Decimal("0.00")


def test_unreachable_goal_returns_none_completion():
    assert projections.months_to_target(
        Decimal("1000"), Decimal("0"), Decimal("0"), Decimal("0")
    ) is None


def test_all_four_scenarios_present_and_ordered():
    sim = projections.simulate(
        projections.GoalInputs(
            target_amount=Decimal("10000"), months=36,
            safe_monthly_contribution=Decimal("200"),
        )
    )
    names = [s.name for s in sim.scenarios]
    assert set(names) == set(projections.SCENARIOS)
    values = {s.name: s.projected_value for s in sim.scenarios}
    assert values["contributions_only"] < values["lower"] < values["medium"] < values["higher_volatility"]


def test_contribution_shortfall_reported():
    sim = projections.simulate(
        projections.GoalInputs(
            target_amount=Decimal("50000"), months=12,
            safe_monthly_contribution=Decimal("100"),
        )
    )
    assert sim.achievable is False
    assert sim.contribution_shortfall > 0
    assert sim.goal_gap > 0


# --- price-increase detection (§12) ----------------------------------------


def _history(merchant, amounts, category=Category.SUBSCRIPTION):
    """Build (pattern, history) for the price-change detector."""
    rows = [
        txn(date(2026, m, 17), merchant, amt, category=category, merchant=merchant)
        for m, amt in enumerate(amounts, start=1)
    ]
    pats = recurrence.detect_recurring(rows)
    hist = {merchant: [(t.date, t.amount, t.id) for t in rows]}
    return pats, hist


def test_settled_price_hike_is_still_detected():
    """A hike three months ago that has been stable since is still a hike.

    Comparing only the latest two payments would report nothing here.
    """
    pats, hist = _history("CloudVault", ["9.99", "9.99", "9.99", "13.99", "13.99", "13.99"])
    changes = price_changes.detect_price_changes(pats, hist)
    assert len(changes) == 1
    c = changes[0]
    assert c.previous_amount == Decimal("9.99")
    assert c.current_amount == Decimal("13.99")
    assert c.percentage_increase == Decimal("40.0")
    assert c.first_date_of_new_price == date(2026, 4, 17)
    assert len(c.evidence_transaction_ids) == 2


def test_fluctuating_merchant_reports_no_price_change():
    """Discretionary spend at one merchant has no 'price' to rise."""
    pats, hist = _history(
        "Shell Fuel", ["41.99", "22.50", "68.10", "31.75", "55.40", "62.99"],
        category=Category.FUEL,
    )
    assert price_changes.detect_price_changes(pats, hist) == []


def test_variable_utility_bill_is_not_a_silent_price_increase():
    """A cold month is not a tariff change."""
    pats, hist = _history(
        "City Power", ["80.00", "94.00", "76.00", "88.00", "101.00", "114.00"],
        category=Category.UTILITIES,
    )
    assert price_changes.detect_price_changes(pats, hist) == []


def test_two_payment_merchant_cannot_produce_a_price_step():
    """$20 then $60 is two purchases, not a 200% price rise."""
    pats, hist = _history("Odd Shop", ["20.00", "60.00"], category=Category.SHOPPING)
    assert price_changes.detect_price_changes(pats, hist) == []


def test_price_decrease_is_not_reported_as_increase():
    pats, hist = _history("CloudVault", ["13.99", "13.99", "13.99", "9.99", "9.99", "9.99"])
    assert price_changes.detect_price_changes(pats, hist) == []


def test_sub_threshold_hike_ignored():
    """A 10c rise on a $10 subscription is noise, not a silent increase."""
    pats, hist = _history("Tiny Sub", ["9.99", "9.99", "9.99", "10.09", "10.09", "10.09"])
    assert price_changes.detect_price_changes(pats, hist) == []


def test_price_change_confidence_bounded_by_pattern_confidence():
    pats, hist = _history("CloudVault", ["9.99", "9.99", "9.99", "13.99", "13.99", "13.99"])
    c = price_changes.detect_price_changes(pats, hist)[0]
    assert 0.0 < c.confidence <= 1.0
    assert c.annualized_increase == Decimal("48.00")


# --- safe spare: income timing (§6.6) --------------------------------------


def test_next_salary_is_not_counted_as_money_already_received():
    """`expected_income_before_next_income` must exclude the next salary itself.

    Counting it would credit the user with a paycheck they have not been paid
    and inflate every downstream contribution.
    """
    rows = []
    for m in range(1, 5):
        rows.append(
            txn(date(2026, m, 28), "ACME PAYROLL", "3200", direction=Direction.CREDIT,
                category=Category.SALARY_INCOME, merchant="Acme Payroll", balance="2880")
        )
        rows.append(
            txn(date(2026, m, 3), "GREENFIELD RENT", "1450",
                category=Category.RENT_HOUSING, merchant="Greenfield", balance="1430")
        )
    inputs = safe_spare.build_inputs(rows)
    assert inputs.expected_income_before_next_income == Decimal("0.00")
    assert inputs.next_income_date is not None


def test_only_confirmed_recovery_counts_in_contribution():
    """confirmed_recovered_amount is a separate input from safe contribution."""
    g = projections.GoalInputs(
        target_amount=Decimal("1000"), months=10,
        safe_monthly_contribution=Decimal("50"),
        confirmed_recovered_amount=Decimal("20"),
        roundup_contribution=Decimal("30"),
    )
    assert g.monthly_contribution == Decimal("100.00")

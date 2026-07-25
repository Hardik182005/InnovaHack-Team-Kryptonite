"""Spoken-expense parsing tests.

Voice is the entry path for users who cannot read a statement, so the parser
must be held to the same standard as the PDF one: never invent an amount, never
silently mishear a magnitude, and always route uncertainty to confirmation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import Category, Direction
from app.services import spoken_expenses as se


# --- amounts ----------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("I spent 250 rupees on vegetables", "250.00"),
        ("paid 1.5k for medicine", "1500.00"),
        ("bus ticket 40 rupees", "40.00"),
        ("1,250 for clothes", "1250.00"),
        ("spent 99.50 on tea", "99.50"),
    ],
)
def test_digit_amounts(phrase, expected):
    assert se.parse(phrase).amount == Decimal(expected)


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("two thousand five hundred on school fees", "2500.00"),
        ("fifty rupees chai", "50.00"),
        ("ek lakh rent", "100000.00"),
        ("teen sau paanch", "305.00"),
    ],
)
def test_spelled_out_amounts(phrase, expected):
    assert se.parse(phrase).amount == Decimal(expected)


@pytest.mark.parametrize(
    "phrase,expected",
    [
        # "dhai sau" is 2.5 x 100, not 2.5 + 100 — the multiplier must multiply.
        ("dhai sau rupees sabzi", "250.00"),
        ("ढाई सौ रुपये सब्जी", "250.00"),
        ("sava sau", "125.00"),
    ],
)
def test_indian_fractional_hundreds(phrase, expected):
    assert se.parse(phrase, "hi").amount == Decimal(expected)


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("50 hazaar salary", "50000.00"),
        ("do lakh", "200000.00"),
        ("1 crore", "10000000.00"),
    ],
)
def test_indian_numbering_units(phrase, expected):
    """lakh and crore are how amounts are actually spoken in India."""
    assert se.parse(phrase, "hi").amount == Decimal(expected)


@pytest.mark.parametrize("phrase", ["२५० रुपये दवा", "৫০০ টাকা", "௧௦௦ ரூபாய்"])
def test_indic_digits_are_understood(phrase):
    assert se.parse(phrase).amount is not None


# --- the safety rule --------------------------------------------------------


@pytest.mark.parametrize(
    "phrase", ["I bought something", "kuch kharida", "spent money today", ""]
)
def test_never_invents_an_amount(phrase):
    """No number heard means no number reported — never a guess."""
    parsed = se.parse(phrase)
    assert parsed.amount is None
    assert parsed.confidence == 0.0
    if phrase:
        assert "no_amount_heard" in parsed.warnings


def test_every_parse_requires_confirmation():
    """§3.14 — a heard amount is never trusted until the user confirms it."""
    parsed = se.parse("I spent 250 rupees on vegetables")
    assert parsed.needs_confirmation is True


def test_cannot_build_a_transaction_without_an_amount():
    parsed = se.parse("I bought something")
    with pytest.raises(ValueError):
        se.to_transaction(parsed)


# --- categories and direction ----------------------------------------------


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("250 on vegetables", Category.GROCERIES),
        ("सब्ज़ी 250", Category.GROCERIES),
        ("100 for medicine", Category.MEDICAL),
        ("दवा 100", Category.MEDICAL),
        ("40 bus ticket", Category.TRANSPORTATION),
        ("500 petrol", Category.FUEL),
        ("5000 rent", Category.RENT_HOUSING),
        ("2000 school fees", Category.EDUCATION),
        ("300 electricity bill", Category.UTILITIES),
        ("150 chai", Category.DINING_DELIVERY),
    ],
)
def test_multilingual_category_detection(phrase, expected):
    assert se.parse(phrase).category is expected


def test_unrecognised_category_is_unknown_not_guessed():
    parsed = se.parse("450 for zzqq")
    assert parsed.category is Category.UNKNOWN
    assert "category_unrecognised" in parsed.warnings


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("received salary 15000", Direction.CREDIT),
        ("got 500 refund", Direction.CREDIT),
        ("spent 250 on vegetables", Direction.DEBIT),
        ("paid 100 for medicine", Direction.DEBIT),
    ],
)
def test_direction_detection(phrase, expected):
    assert se.parse(phrase).direction is expected


# --- conversion to a Transaction -------------------------------------------


def test_confirmed_expense_becomes_a_transaction():
    parsed = se.parse("I spent 250 rupees on vegetables")
    txn = se.to_transaction(parsed, currency="INR")
    assert txn.amount == Decimal("250.00")
    assert txn.category is Category.GROCERIES
    assert txn.direction is Direction.DEBIT
    assert txn.parser == "voice"
    assert txn.currency == "INR"
    # Marked as user-supplied so re-categorization cannot overwrite it.
    assert txn.user_overridden is True


def test_spoken_transaction_flows_into_the_engines():
    """A spoken expense must behave exactly like a parsed statement row."""
    from app.services import roundups

    parsed = se.parse("I spent 4 rupees 30 paise on tea")
    txn = se.to_transaction(se.parse("I spent 4.30 on tea"))
    result = roundups.calculate_roundups([txn])
    assert result.historical_round_up_total == Decimal("0.70")


def test_essential_spoken_expense_is_excluded_from_roundups():
    """Guardrail §25.4 holds for voice input too."""
    from app.services import roundups

    txn = se.to_transaction(se.parse("5000 rent"))
    result = roundups.calculate_roundups([txn])
    assert result.eligible_count == 0
    assert result.lines[0].reason.startswith("excluded_category")


# --- description cleanup ----------------------------------------------------


def test_description_strips_filler_and_numbers():
    parsed = se.parse("I spent 250 rupees on vegetables")
    assert "250" not in parsed.description
    assert "rupees" not in parsed.description.lower()
    assert "vegetable" in parsed.description.lower()

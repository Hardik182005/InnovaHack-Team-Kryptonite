"""Parse spoken expense phrases into transactions.

Built for users who cannot upload a bank statement — or cannot read one. They
say what they spent, and this turns the words into the same `Transaction`
objects the statement pipeline produces, so every downstream engine (Safe Spare,
round-ups, leaks) works identically whether the data was spoken or parsed from a
PDF.

Deterministic and offline. No LLM computes an amount here (§3.7): the numerals
are extracted by explicit rules, and anything ambiguous is returned with a low
confidence for the user to confirm on screen before it counts.

Supports the number words and spending vocabulary of the major Indian languages
alongside English, plus Indian numbering units (lakh, crore) and the Devanagari,
Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati and Gurmukhi digit sets.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from ..models.enums import Category, Direction
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "spoken_expenses.v1"

#: Indian numbering units. `lakh` and `crore` are how amounts are actually
#: spoken across the subcontinent; a parser that only knows "thousand" and
#: "million" mishears the majority of real phrases.
MULTIPLIERS: Dict[str, Decimal] = {
    "hundred": Decimal("100"), "सौ": Decimal("100"), "শত": Decimal("100"),
    "நூறு": Decimal("100"), "వంద": Decimal("100"), "ನೂರು": Decimal("100"),
    "sau": Decimal("100"),
    "thousand": Decimal("1000"), "hazaar": Decimal("1000"), "hazar": Decimal("1000"),
    "हज़ार": Decimal("1000"), "हजार": Decimal("1000"), "হাজার": Decimal("1000"),
    "ஆயிரம்": Decimal("1000"), "వేయి": Decimal("1000"), "ಸಾವಿರ": Decimal("1000"),
    "lakh": Decimal("100000"), "lac": Decimal("100000"), "लाख": Decimal("100000"),
    "লাখ": Decimal("100000"), "லட்சம்": Decimal("100000"), "లక్ష": Decimal("100000"),
    "crore": Decimal("10000000"), "करोड़": Decimal("10000000"), "কোটি": Decimal("10000000"),
    "k": Decimal("1000"),
}

#: Spelled-out numbers. English plus the most common Hindi/Urdu forms, which
#: dictation frequently returns as words rather than digits.
NUMBER_WORDS: Dict[str, Decimal] = {
    "zero": Decimal(0), "one": Decimal(1), "two": Decimal(2), "three": Decimal(3),
    "four": Decimal(4), "five": Decimal(5), "six": Decimal(6), "seven": Decimal(7),
    "eight": Decimal(8), "nine": Decimal(9), "ten": Decimal(10),
    "eleven": Decimal(11), "twelve": Decimal(12), "thirteen": Decimal(13),
    "fourteen": Decimal(14), "fifteen": Decimal(15), "sixteen": Decimal(16),
    "seventeen": Decimal(17), "eighteen": Decimal(18), "nineteen": Decimal(19),
    "twenty": Decimal(20), "thirty": Decimal(30), "forty": Decimal(40),
    "fifty": Decimal(50), "sixty": Decimal(60), "seventy": Decimal(70),
    "eighty": Decimal(80), "ninety": Decimal(90),
    # Hindi / Urdu
    "ek": Decimal(1), "do": Decimal(2), "teen": Decimal(3), "char": Decimal(4),
    "paanch": Decimal(5), "panch": Decimal(5), "chhe": Decimal(6), "saat": Decimal(7),
    "aath": Decimal(8), "nau": Decimal(9), "das": Decimal(10), "bees": Decimal(20),
    "pachas": Decimal(50), "pachaas": Decimal(50),
    "एक": Decimal(1), "दो": Decimal(2), "तीन": Decimal(3), "चार": Decimal(4),
    "पाँच": Decimal(5), "पांच": Decimal(5), "छह": Decimal(6), "सात": Decimal(7),
    "आठ": Decimal(8), "नौ": Decimal(9), "दस": Decimal(10),
    "बीस": Decimal(20), "पचास": Decimal(50),
    # "two and a half hundred" style — very common when saying 250
    "dhai": Decimal("2.5"), "ढाई": Decimal("2.5"),
    "sava": Decimal("1.25"), "सवा": Decimal("1.25"),
    "sade": Decimal("0.5"), "साढ़े": Decimal("0.5"),
}

#: Words that mean "this was money going out" / "coming in".
CREDIT_WORDS = {
    "received", "got", "earned", "income", "salary", "credited", "refund",
    "मिला", "मिले", "आया", "वेतन", "जमा", "পেয়েছি", "வந்தது", "వచ్చింది",
}

#: Category keywords by language. Deliberately literal — this is a lookup, not
#: an inference engine, so a wrong guess is visible and correctable.
CATEGORY_WORDS: Dict[Category, List[str]] = {
    Category.GROCERIES: [
        "grocery", "groceries", "vegetable", "vegetables", "sabzi", "sabji",
        "kirana", "ration", "market", "fruits", "milk", "doodh",
        "सब्जी", "सब्ज़ी", "किराना", "राशन", "दूध", "সবজি", "காய்கறி", "కూరగాయలు",
        "ತರಕಾರಿ", "പച്ചക്കറി", "શાકભાજી", "ਸਬਜ਼ੀ",
    ],
    Category.DINING_DELIVERY: [
        "food", "lunch", "dinner", "breakfast", "restaurant", "hotel", "tea",
        "chai", "coffee", "snack", "khana", "swiggy", "zomato",
        "खाना", "चाय", "नाश्ता", "খাবার", "চা", "உணவு", "టీ", "ಊಟ", "ഭക്ഷണം",
    ],
    Category.TRANSPORTATION: [
        "bus", "train", "auto", "rickshaw", "taxi", "uber", "ola", "ticket",
        "travel", "fare", "बस", "ट्रेन", "ऑटो", "किराया", "টিকিট", "பேருந்து",
        "బస్సు", "ಬಸ್", "ബസ്",
    ],
    Category.FUEL: [
        "petrol", "diesel", "fuel", "gas", "पेट्रोल", "डीजल", "পেট্রোল", "பெட்ரோல்",
    ],
    Category.MEDICAL: [
        "medicine", "doctor", "hospital", "clinic", "medical", "dawa", "dawai",
        "दवा", "दवाई", "डॉक्टर", "अस्पताल", "ওষুধ", "மருந்து", "మందు", "ಔಷಧಿ", "മരുന്ന്",
    ],
    Category.UTILITIES: [
        "electricity", "water bill", "gas bill", "recharge", "mobile", "internet",
        "bijli", "बिजली", "पानी", "रिचार्ज", "বিদ্যুৎ", "மின்சாரம்", "కరెంట్",
    ],
    Category.RENT_HOUSING: [
        "rent", "kiraya", "किराया", "भाड़ा", "ভাড়া", "வாடகை", "అద్దె", "ಬಾಡಿಗೆ",
    ],
    Category.EDUCATION: [
        "school", "fees", "tuition", "college", "books", "स्कूल", "फीस", "किताब",
        "স্কুল", "பள்ளி", "పాఠశాల",
    ],
    Category.SHOPPING: [
        "clothes", "shopping", "shirt", "shoes", "kapde", "कपड़े", "जूते",
        "জামা", "துணி", "బట్టలు",
    ],
    Category.ENTERTAINMENT: [
        "movie", "cinema", "game", "फिल्म", "सिनेमा", "সিনেমা", "திரைப்படம்",
    ],
    Category.SALARY_INCOME: [
        "salary", "wages", "pay", "वेतन", "तनख्वाह", "বেতন", "சம்பளம்", "జీతం",
    ],
}


@dataclass
class SpokenExpense:
    """One parsed utterance."""

    transcript: str
    amount: Optional[Decimal]
    description: str
    category: Category
    direction: Direction
    confidence: float
    language: str = "en"
    needs_confirmation: bool = True
    warnings: List[str] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION


def _normalize_digits(text: str) -> str:
    """Convert Devanagari/Bengali/Tamil/etc. digits to ASCII.

    `unicodedata.digit` handles every Unicode decimal digit, so this covers all
    Indic scripts without a per-script table.
    """
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except (TypeError, ValueError):
                pass
        out.append(ch)
    return "".join(out)


_NUMERIC = re.compile(r"(\d[\d,]*(?:\.\d{1,2})?)")


def _amount_from_digits(text: str) -> Optional[Decimal]:
    """Digits, optionally followed by an Indian numbering unit."""
    match = _NUMERIC.search(text)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None

    tail = text[match.end() : match.end() + 24].lower()
    for word, factor in MULTIPLIERS.items():
        if re.search(r"\b%s" % re.escape(word), tail):
            return value * factor
    return value


def _amount_from_words(text: str) -> Optional[Decimal]:
    """Spelled-out numbers, including 'dhai sau' (2.5 x 100 = 250)."""
    tokens = re.split(r"[\s,]+", text.lower())
    total = Decimal(0)
    current = Decimal(0)
    seen = False

    for token in tokens:
        token = token.strip(".!?॥।")
        if token in NUMBER_WORDS:
            current += NUMBER_WORDS[token]
            seen = True
        elif token in MULTIPLIERS:
            factor = MULTIPLIERS[token]
            current = (current if current else Decimal(1)) * factor
            if factor >= 1000:
                total += current
                current = Decimal(0)
            seen = True

    total += current
    return total if seen and total > 0 else None


def _category_for(text: str) -> Category:
    lowered = text.lower()
    for category, words in CATEGORY_WORDS.items():
        for word in words:
            if word in lowered:
                return category
    return Category.UNKNOWN


def _direction_for(text: str) -> Direction:
    lowered = text.lower()
    return Direction.CREDIT if any(w in lowered for w in CREDIT_WORDS) else Direction.DEBIT


_FILLER = re.compile(
    r"\b(i|we|spent|paid|bought|on|for|of|the|a|an|today|yesterday|rupees?|rs|inr|"
    r"maine|kharcha|kharch|kiya|kiye|pe|par|ka|ki|ke|"
    r"मैंने|खर्च|किया|किये|रुपये|रुपए|पर|का|की|के|"
    r"আমি|খরচ|টাকা|நான்|செலவு|ரூபாய்|నేను|ఖర్చు|రూపాయలు)\b",
    re.I,
)


def parse(transcript: str, language: str = "en") -> SpokenExpense:
    """Turn one spoken phrase into a structured expense.

    Returns `amount=None` rather than guessing when no number is audible: an
    invented amount would flow into the Safe Spare calculation, which is exactly
    what this product exists to prevent.
    """
    raw = (transcript or "").strip()
    if not raw:
        return SpokenExpense(
            transcript="", amount=None, description="", category=Category.UNKNOWN,
            direction=Direction.DEBIT, confidence=0.0, language=language,
            warnings=["empty_transcript"],
        )

    text = _normalize_digits(raw)
    amount = _amount_from_digits(text)
    method_confidence = 0.9
    if amount is None:
        amount = _amount_from_words(text)
        method_confidence = 0.7

    description = _FILLER.sub(" ", _NUMERIC.sub(" ", text))
    for word in MULTIPLIERS:
        description = re.sub(r"\b%s\b" % re.escape(word), " ", description, flags=re.I)
    description = re.sub(r"\s{2,}", " ", description).strip(" .,-")

    category = _category_for(text)
    direction = _direction_for(text)

    warnings: List[str] = []
    confidence = method_confidence
    if amount is None:
        confidence = 0.0
        warnings.append("no_amount_heard")
    if category is Category.UNKNOWN:
        confidence *= 0.8
        warnings.append("category_unrecognised")
    if not description:
        confidence *= 0.8
        warnings.append("no_description_heard")

    return SpokenExpense(
        transcript=raw,
        amount=money(amount) if amount is not None else None,
        description=description or raw,
        category=category,
        direction=direction,
        confidence=round(min(1.0, confidence), 2),
        language=language,
        # Always true: a spoken amount is never trusted until the user confirms
        # what was heard (§3.14).
        needs_confirmation=True,
        warnings=warnings,
    )


def to_transaction(
    expense: SpokenExpense, on: Optional[date] = None, currency: str = "INR"
) -> Transaction:
    """Convert a *confirmed* spoken expense into a Transaction."""
    if expense.amount is None:
        raise ValueError("cannot build a transaction without an amount")
    return Transaction(
        date=on or date.today(),
        description=expense.description or expense.transcript,
        amount=expense.amount,
        direction=expense.direction,
        category=expense.category,
        category_confidence=expense.confidence,
        category_method="spoken_entry",
        normalized_merchant=expense.description or None,
        merchant_method="spoken_entry",
        merchant_confidence=expense.confidence,
        currency=currency,
        parser="voice",
        extraction_confidence=expense.confidence,
        validation_warnings=list(expense.warnings),
        user_overridden=True,  # the user confirmed what was heard
    )

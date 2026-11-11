"""Parse values, units and periods as written on slides."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCALES: list[tuple[str, float]] = [
    (r"трлн|trln|trillion", 1e12),
    (r"млрд|миллиард\w*|bln|billion", 1e9),
    (r"млн|миллион\w*|mln|million", 1e6),
    (r"тыс\.?|тысяч\w*|thousand", 1e3),
]
_SUFFIX_SCALES = {"t": 1e12, "b": 1e9, "m": 1e6, "k": 1e3}
_NUMBER = re.compile(r"(?<!\d)-?\d(?:[\d\u00a0\u202f ]*\d)?(?:[.,]\d+)?")
_YEAR = re.compile(r"(?<!\d)(20[0-4]\d|19\d\d)(?!\d)")
_YEAR_RANGE = re.compile(r"(?<!\d)(20[0-4]\d)\s*[-–—]\s*(20[0-4]\d)(?!\d)")


@dataclass(frozen=True)
class ParsedValue:
    amount: float | None
    amount_high: float | None
    unit_kind: str


def _to_float(token: str) -> float | None:
    cleaned = re.sub(r"[\s  ]", "", token).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _unit_kind(text: str) -> str:
    low = text.lower()
    if "%" in low or "процент" in low:
        return "percent"
    if "$" in low or "usd" in low or "долл" in low:
        return "USD"
    if "€" in low or "eur" in low or "евро" in low:
        return "EUR"
    if "₽" in low or "руб" in low or "rub" in low or re.search(r"(?<![а-яё])р\.", low):
        return "RUB"
    if re.search(r"чел|сотрудник|шт|клиент|компан|employee|people", low):
        return "count"
    return "other"


def _scale(text: str) -> float:
    low = text.lower()
    for pattern, factor in _SCALES:
        if re.search(pattern, low):
            return factor
    match = re.search(r"\d\s*([tbmk])(?![a-zа-я])", low)
    return _SUFFIX_SCALES[match[1]] if match else 1.0


def parse_value(value: str, unit: str = "") -> ParsedValue:
    """Parse "1 030" + "млн руб." or "$84B"; ranges keep both ends."""
    combined = f"{value} {unit}".strip()
    numbers = [n for n in (_to_float(m) for m in _NUMBER.findall(value)) if n is not None]
    if not numbers:
        return ParsedValue(None, None, _unit_kind(combined))
    # A scale written next to the number wins over the unit: "$700 млн" with unit "млрд $".
    factor = _scale(value)
    if factor == 1.0:
        factor = _scale(combined)
    low = numbers[0] * factor
    is_range = len(numbers) >= 2 and re.search(r"\d\s*[-–—]\s*\d|\bдо\b", value) is not None
    high = numbers[1] * factor if is_range else None
    return ParsedValue(low, high, _unit_kind(combined))


def parse_years(period: str) -> list[int]:
    """Return every year covered: "2026-2028" expands, "2021 П" gives [2021]."""
    text = period or ""
    years: set[int] = set()
    for start, end in _YEAR_RANGE.findall(text):
        first, last = int(start), int(end)
        if first <= last <= first + 30:
            years.update(range(first, last + 1))
    years.update(int(y) for y in _YEAR.findall(text))
    return sorted(years)


def year_ranges(text: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in _YEAR_RANGE.findall(text or "") if int(a) < int(b)]


def years_in_text(text: str) -> list[int]:
    return sorted({int(y) for y in _YEAR.findall(text or "")})


def value_in_text(value: str, text: str) -> bool:
    """True when every number as written appears in the slide text, ignoring digit grouping."""
    numbers = _NUMBER.findall(value or "")
    if not numbers:
        return False
    for number in numbers:
        pieces = re.sub(r"[\s\u00a0\u202f]", "", number).lstrip("-")
        pattern = r"[\s\u00a0\u202f]?".join(
            "[.,]" if char in ".," else re.escape(char) for char in pieces
        )
        if not re.search(rf"(?<![\d.,]){pattern}(?![\d]|[.,]\d)", text or ""):
            return False
    return True


def same_amount(a: float | None, b: float | None, tolerance: float = 0.005) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    return abs(a - b) <= tolerance * max(abs(a), abs(b))

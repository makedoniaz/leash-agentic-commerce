import re


_CURRENCY_PATTERNS = {
    "CHF": re.compile(
        r"(?i)(?:\bCHF\b|\bSwiss\s+francs?\b|\bfrancs?\b|\bfranks?\b|\bSFr\.?\b)"
    ),
    "USD": re.compile(r"(?i)(?:\bUSD\b|\bUS\s+dollars?\b|\bdollars?\b|\$)"),
    "EUR": re.compile(r"(?i)(?:\bEUR\b|\beuros?\b|€)"),
}


def detect_explicit_currency(text: str) -> str | None:
    """Return one explicitly stated supported currency, otherwise null."""
    matches = [
        currency
        for currency, pattern in _CURRENCY_PATTERNS.items()
        if pattern.search(text)
    ]
    return matches[0] if len(matches) == 1 else None


def detect_explicit_period_days(text: str) -> int | None:
    """Normalize one explicit spending period; reject conflicting periods."""
    lowered = text.lower()
    periods: set[int] = set()

    named_periods = (
        (r"\b(?:daily|each day|every day|per day)\b", 1),
        (r"\b(?:weekly|each week|every week|per week)\b", 7),
        (r"\b(?:monthly|each month|every month|per month)\b", 30),
        (r"\b(?:yearly|annually|each year|every year|per year)\b", 365),
    )
    for pattern, days in named_periods:
        if re.search(pattern, lowered):
            periods.add(days)

    unit_days = {
        "day": 1,
        "days": 1,
        "week": 7,
        "weeks": 7,
        "month": 30,
        "months": 30,
        "year": 365,
        "years": 365,
    }
    for count, unit in re.findall(
        r"\bevery\s+(\d+)\s+(days?|weeks?|months?|years?)\b", lowered
    ):
        periods.add(int(count) * unit_days[unit])

    return periods.pop() if len(periods) == 1 else None

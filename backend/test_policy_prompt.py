from policy_prompt import detect_explicit_currency, detect_explicit_period_days


def test_currency_detection() -> None:
    assert detect_explicit_currency("Spend up to CHF 100") == "CHF"
    assert detect_explicit_currency("Spend up to 100 Swiss francs") == "CHF"
    assert detect_explicit_currency("Spend up to $100") == "USD"
    assert detect_explicit_currency("Spend up to 100 euros") == "EUR"
    assert detect_explicit_currency("Spend up to 100") is None


def test_conflicting_currencies_are_rejected() -> None:
    assert detect_explicit_currency("Spend CHF 100 or USD 100") is None


def test_period_detection() -> None:
    assert detect_explicit_period_days("a daily budget") == 1
    assert detect_explicit_period_days("a weekly budget") == 7
    assert detect_explicit_period_days("a monthly budget") == 30
    assert detect_explicit_period_days("a yearly budget") == 365
    assert detect_explicit_period_days("a purchase budget") is None


def test_explicit_period_detection() -> None:
    assert detect_explicit_period_days("every 14 days") == 14
    assert detect_explicit_period_days("every 2 weeks") == 14
    assert detect_explicit_period_days("daily or weekly") is None

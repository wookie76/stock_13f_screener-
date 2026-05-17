from stock_13f_screener.cusip import is_valid_cusip, normalize_cusip, safe_normalize_cusip


def test_normalize_cusip() -> None:
    assert normalize_cusip("037 833-100") == "037833100"


def test_valid_known_cusips() -> None:
    assert is_valid_cusip("037833100")
    assert is_valid_cusip("594918104")


def test_safe_normalize_invalid() -> None:
    assert safe_normalize_cusip("bad") is None

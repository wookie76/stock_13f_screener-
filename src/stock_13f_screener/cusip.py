from __future__ import annotations

import string

_CUSIP_CHARS = {char: idx for idx, char in enumerate(string.digits + string.ascii_uppercase)}
_CUSIP_CHARS.update({"*": 36, "@": 37, "#": 38})


def normalize_cusip(value: str) -> str:
    cusip = value.strip().upper().replace("-", "").replace(" ", "")
    if len(cusip) != 9:
        raise ValueError(f"CUSIP must be 9 characters, got {len(cusip)}: {value!r}")
    invalid = [char for char in cusip if char not in _CUSIP_CHARS]
    if invalid:
        raise ValueError(f"CUSIP has invalid characters {invalid}: {value!r}")
    return cusip


def is_valid_cusip(value: str) -> bool:
    try:
        cusip = normalize_cusip(value)
    except ValueError:
        return False

    total = 0
    for index, char in enumerate(cusip[:8]):
        digit = _CUSIP_CHARS[char]
        if index % 2 == 1:
            digit *= 2
        total += digit // 10 + digit % 10

    check_digit = (10 - total % 10) % 10
    return cusip[-1].isdigit() and check_digit == int(cusip[-1])


def safe_normalize_cusip(value: object) -> str | None:
    if value is None:
        return None
    try:
        return normalize_cusip(str(value))
    except ValueError:
        return None

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ManagerType(StrEnum):
    PASSIVE_GIANT = "passive_giant"
    ACTIVE_SIGNAL_RICH = "active_signal_rich"
    BANK_BROKER_COMPLEX = "bank_broker_complex"


@dataclass(frozen=True)
class Institution:
    name: str
    cik: str
    manager_type: ManagerType
    signal_weight: float
    noise_note: str


INSTITUTIONS: dict[str, Institution] = {
    "BlackRock": Institution(
        "BlackRock",
        "0001364742",
        ManagerType.PASSIVE_GIANT,
        0.40,
        "Huge passive/index exposure; ownership often reflects index inclusion.",
    ),
    "Vanguard": Institution(
        "Vanguard",
        "0000102909",
        ManagerType.PASSIVE_GIANT,
        0.40,
        "Huge passive/index exposure; better for sponsorship than conviction.",
    ),
    "State Street": Institution(
        "State Street",
        "0000093751",
        ManagerType.PASSIVE_GIANT,
        0.35,
        "Large ETF/index manager; baseline ownership signal.",
    ),
    "Geode Capital": Institution(
        "Geode Capital",
        "0001214717",
        ManagerType.PASSIVE_GIANT,
        0.35,
        "Large index/systematic manager; often mirrors passive exposure.",
    ),
    "Charles Schwab Investment Management": Institution(
        "Charles Schwab Investment Management",
        "0000884546",
        ManagerType.PASSIVE_GIANT,
        0.30,
        "Large passive/ETF manager; useful for broad sponsorship checks.",
    ),
    "Berkshire Hathaway": Institution(
        "Berkshire Hathaway",
        "0001067983",
        ManagerType.ACTIVE_SIGNAL_RICH,
        1.00,
        "Concentrated active manager; changes can be more meaningful.",
    ),
    "Citadel Advisors": Institution(
        "Citadel Advisors",
        "0001423053",
        ManagerType.ACTIVE_SIGNAL_RICH,
        0.75,
        "Multi-strategy; signal-rich but can include hedges/options.",
    ),
    "FMR / Fidelity": Institution(
        "FMR / Fidelity",
        "0000315066",
        ManagerType.ACTIVE_SIGNAL_RICH,
        0.70,
        "Large active/passive mix; useful but not pure conviction.",
    ),
    "Morgan Stanley": Institution(
        "Morgan Stanley",
        "0000895421",
        ManagerType.BANK_BROKER_COMPLEX,
        0.25,
        "May aggregate many desks/accounts; noisy directional signal.",
    ),
    "Goldman Sachs": Institution(
        "Goldman Sachs",
        "0000886982",
        ManagerType.BANK_BROKER_COMPLEX,
        0.25,
        "Prime brokerage/trading/asset-management mix; interpret carefully.",
    ),
    "Bank of America": Institution(
        "Bank of America",
        "0000070858",
        ManagerType.BANK_BROKER_COMPLEX,
        0.20,
        "Large complex institution; holdings may not imply one investment view.",
    ),
    "JPMorgan Chase": Institution(
        "JPMorgan Chase",
        "0000019617",
        ManagerType.BANK_BROKER_COMPLEX,
        0.25,
        "Bank, broker, and asset-management exposure can be mixed.",
    ),
    "UBS Group": Institution(
        "UBS Group",
        "0001610520",
        ManagerType.BANK_BROKER_COMPLEX,
        0.20,
        "Global bank/broker/wealth platform; useful coverage, noisy signal.",
    ),
}


def institution_by_cik() -> dict[str, Institution]:
    return {institution.cik: institution for institution in INSTITUTIONS.values()}


def select_institutions(names: list[str] | None = None) -> list[Institution]:
    if not names:
        return list(INSTITUTIONS.values())
    missing = sorted(set(names) - set(INSTITUTIONS))
    if missing:
        raise ValueError(f"Unknown institutions: {missing}")
    return [INSTITUTIONS[name] for name in names]

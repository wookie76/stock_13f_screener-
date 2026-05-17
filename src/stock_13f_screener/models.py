from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from stock_13f_screener.cusip import normalize_cusip
from stock_13f_screener.managers import ManagerType


class MappingStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    MISSING_TICKER = "missing_ticker"
    INVALID_CUSIP = "invalid_cusip"


class HoldingRow(BaseModel):
    filing_accession: str | None = None
    filing_date: str | None = None
    report_period: str | None = None
    institution_cik: str
    institution_name: str
    manager_type: ManagerType
    signal_weight: float = 0.0
    issuer_name: str | None = None
    class_title: str | None = None
    cusip: str
    value_usd_thousands: float | None = None
    shares: float | None = None
    share_type: str | None = None
    put_call: str | None = None
    investment_discretion: str | None = None
    voting_sole: float | None = None
    voting_shared: float | None = None
    voting_none: float | None = None
    source_file: str | None = None
    parsed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("cusip")
    @classmethod
    def _normalize_cusip(cls, value: str) -> str:
        return normalize_cusip(value)


class CusipMappingRow(BaseModel):
    cusip: str
    ticker: str | None = None
    figi: str | None = None
    composite_figi: str | None = None
    share_class_figi: str | None = None
    name: str | None = None
    exchange_code: str | None = None
    market_sector: str | None = None
    security_type: str | None = None
    security_type_2: str | None = None
    raw_rank: int = -1
    status: MappingStatus = MappingStatus.UNRESOLVED
    error: str | None = None
    source: str = "openfigi"
    resolved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("cusip")
    @classmethod
    def _normalize_cusip(cls, value: str) -> str:
        return normalize_cusip(value)

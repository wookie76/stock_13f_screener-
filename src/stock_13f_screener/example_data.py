from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_13f_screener.parquet_store import TableStore


def make_example_data(output_dir: Path) -> dict[str, Path]:
    silver = output_dir / "silver"
    gold = output_dir / "gold"
    rows = [
        {
            "filing_accession": "example-1",
            "filing_date": "2026-02-14",
            "report_period": "2025-12-31",
            "institution_cik": "0001364742",
            "institution_name": "BlackRock",
            "manager_type": "passive_giant",
            "signal_weight": 0.4,
            "issuer_name": "APPLE INC",
            "class_title": "COM",
            "cusip": "037833100",
            "value_usd_thousands": 1000000.0,
            "shares": 1000000.0,
            "share_type": "SH",
            "put_call": None,
            "ticker": "AAPL",
            "figi": "BBG000B9XRY4",
            "status": "resolved",
            "is_resolved": True,
        },
        {
            "filing_accession": "example-2",
            "filing_date": "2026-02-14",
            "report_period": "2025-12-31",
            "institution_cik": "0001067983",
            "institution_name": "Berkshire Hathaway",
            "manager_type": "active_signal_rich",
            "signal_weight": 1.0,
            "issuer_name": "APPLE INC",
            "class_title": "COM",
            "cusip": "037833100",
            "value_usd_thousands": 500000.0,
            "shares": 500000.0,
            "share_type": "SH",
            "put_call": None,
            "ticker": "AAPL",
            "figi": "BBG000B9XRY4",
            "status": "resolved",
            "is_resolved": True,
        },
        {
            "filing_accession": "example-3",
            "filing_date": "2026-02-14",
            "report_period": "2025-12-31",
            "institution_cik": "0000895421",
            "institution_name": "Morgan Stanley",
            "manager_type": "bank_broker_complex",
            "signal_weight": 0.25,
            "issuer_name": "MICROSOFT CORP",
            "class_title": "COM",
            "cusip": "594918104",
            "value_usd_thousands": 250000.0,
            "shares": 250000.0,
            "share_type": "SH",
            "put_call": "Call",
            "ticker": "MSFT",
            "figi": "BBG000BPH459",
            "status": "resolved",
            "is_resolved": True,
        },
    ]
    data = pd.DataFrame(rows)
    TableStore(silver, "holdings_resolved").replace(data)
    from stock_13f_screener.analytics import build_gold_tables

    build_gold_tables(data, gold)
    return {
        "holdings": silver / "holdings_resolved.parquet",
        "gold_dir": gold,
    }

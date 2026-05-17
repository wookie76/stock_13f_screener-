import pandas as pd

from stock_13f_screener.analytics import build_latest_holdings, build_ticker_sponsorship


def test_build_ticker_sponsorship() -> None:
    data = pd.DataFrame(
        [
            {
                "institution_cik": "1",
                "institution_name": "BlackRock",
                "manager_type": "passive_giant",
                "signal_weight": 0.4,
                "cusip": "037833100",
                "ticker": "AAPL",
                "report_period": "2025-12-31",
                "put_call": None,
                "value_usd_thousands": 100.0,
            },
            {
                "institution_cik": "2",
                "institution_name": "Berkshire Hathaway",
                "manager_type": "active_signal_rich",
                "signal_weight": 1.0,
                "cusip": "037833100",
                "ticker": "AAPL",
                "report_period": "2025-12-31",
                "put_call": None,
                "value_usd_thousands": 200.0,
            },
        ]
    )
    latest = build_latest_holdings(data)
    summary = build_ticker_sponsorship(latest)
    row = summary.loc[summary["ticker"].eq("AAPL")].iloc[0]
    assert row["passive_giant_count"] == 1
    assert row["active_signal_rich_count"] == 1
    assert row["has_blackrock"]
    assert row["has_berkshire"]

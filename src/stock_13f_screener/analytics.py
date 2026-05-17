from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from stock_13f_screener.managers import ManagerType
from stock_13f_screener.parquet_store import TableStore

SPECIAL_TICKER_PATTERN = r"[A-Z0-9.\-]+"
SPONSORSHIP_SORT_COLUMNS = [
    "institutional_signal_score",
    "weighted_holder_score",
    "log_total_value_usd_thousands",
    "total_institution_count",
    "ticker",
]


def build_latest_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty:
        return holdings.copy()

    required = {"institution_cik", "cusip", "report_period"}
    missing = required - set(holdings.columns)
    if missing:
        raise ValueError(f"Missing required columns for latest holdings: {sorted(missing)}")

    data = holdings.copy()
    data["report_period_sort"] = pd.to_datetime(data["report_period"], errors="coerce")
    data = data.sort_values(["institution_cik", "cusip", "report_period_sort"])

    duplicate_keys = ["institution_cik", "cusip", "put_call"]
    duplicate_keys = [column for column in duplicate_keys if column in data.columns]
    latest = data.drop_duplicates(subset=duplicate_keys, keep="last")

    return latest.drop(columns=["report_period_sort"], errors="ignore").reset_index(drop=True)


def build_ticker_sponsorship(latest_holdings: pd.DataFrame) -> pd.DataFrame:
    if latest_holdings.empty or "ticker" not in latest_holdings.columns:
        return pd.DataFrame()

    data = latest_holdings[latest_holdings["ticker"].notna()].copy()
    if data.empty:
        return pd.DataFrame()

    grouped = data.groupby("ticker", dropna=False)
    summary = grouped.agg(
        total_institution_count=("institution_cik", "nunique"),
        total_value_usd_thousands=("value_usd_thousands", "sum"),
        weighted_holder_score=("signal_weight", "sum"),
    ).reset_index()

    type_counts = _build_manager_type_counts(data)
    flags = _build_holder_flags(data)

    result = summary.merge(type_counts, on="ticker", how="left").merge(
        flags,
        on="ticker",
        how="left",
    )
    result = result.rename(
        columns={
            ManagerType.PASSIVE_GIANT.value: "passive_giant_count",
            ManagerType.ACTIVE_SIGNAL_RICH.value: "active_signal_rich_count",
            ManagerType.BANK_BROKER_COMPLEX.value: "bank_broker_complex_count",
        }
    )

    result = _ensure_count_columns(result)
    result["institutional_signal_score"] = result.apply(score_sponsorship_row, axis=1)
    result = enrich_ticker_sponsorship(result)
    return sort_ticker_sponsorship(result).reset_index(drop=True)


def enrich_ticker_sponsorship(data: pd.DataFrame) -> pd.DataFrame:
    """Add dashboard-friendly EDA columns without changing raw ticker."""
    if data.empty:
        return data.copy()

    result = data.copy()
    result = result.drop(columns=["Unnamed: 0"], errors="ignore")

    if "ticker" in result.columns:
        result["ticker_raw"] = result["ticker"].astype("string")
        result["ticker_display"] = result["ticker_raw"]
        result["is_special_ticker"] = ~result["ticker_raw"].str.fullmatch(
            SPECIAL_TICKER_PATTERN,
            na=False,
        )
    else:
        result["ticker_raw"] = pd.Series(dtype="string")
        result["ticker_display"] = pd.Series(dtype="string")
        result["is_special_ticker"] = pd.Series(dtype="bool")

    value = pd.to_numeric(
        result.get("total_value_usd_thousands", pd.Series(0, index=result.index)),
        errors="coerce",
    ).fillna(0)
    result["log_total_value_usd_thousands"] = np.log1p(value.clip(lower=0))

    score = pd.to_numeric(
        result.get("institutional_signal_score", pd.Series(0, index=result.index)),
        errors="coerce",
    ).fillna(0)
    weighted = pd.to_numeric(
        result.get("weighted_holder_score", pd.Series(0, index=result.index)),
        errors="coerce",
    ).fillna(0)
    breadth = pd.to_numeric(
        result.get("total_institution_count", pd.Series(0, index=result.index)),
        errors="coerce",
    ).fillna(0)

    result["rank_sort_score"] = (
        score * 1_000_000
        + weighted * 10_000
        + result["log_total_value_usd_thousands"] * 100
        + breadth
    )

    return result


def sort_ticker_sponsorship(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data.copy()

    sort_columns = [column for column in SPONSORSHIP_SORT_COLUMNS if column in data.columns]
    if not sort_columns:
        return data.sort_values("ticker") if "ticker" in data.columns else data

    ascending = [False] * len(sort_columns)
    if sort_columns[-1] == "ticker":
        ascending[-1] = True
    return data.sort_values(sort_columns, ascending=ascending)


def build_position_deltas(holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()

    required = {"institution_cik", "cusip", "report_period", "shares", "value_usd_thousands"}
    missing = required - set(holdings.columns)
    if missing:
        raise ValueError(f"Missing required columns for deltas: {sorted(missing)}")

    data = holdings.copy()
    data["report_period_sort"] = pd.to_datetime(data["report_period"], errors="coerce")

    key_cols = ["institution_cik", "cusip", "put_call"]
    key_cols = [column for column in key_cols if column in data.columns]

    data = data.sort_values([*key_cols, "report_period_sort"])
    data["previous_shares"] = data.groupby(key_cols, dropna=False)["shares"].shift(1)
    data["previous_value"] = data.groupby(key_cols, dropna=False)["value_usd_thousands"].shift(1)
    data["current_shares"] = data["shares"]
    data["current_value"] = data["value_usd_thousands"]
    data["share_delta"] = data["current_shares"] - data["previous_shares"]
    data["value_delta"] = data["current_value"] - data["previous_value"]
    data["share_delta_pct"] = _safe_pct_delta(data["current_shares"], data["previous_shares"])
    data["value_delta_pct"] = _safe_pct_delta(data["current_value"], data["previous_value"])
    data["position_status"] = np.select(
        [
            data["previous_shares"].isna() & data["current_shares"].gt(0),
            data["current_shares"].gt(data["previous_shares"]),
            data["current_shares"].lt(data["previous_shares"]),
            data["current_shares"].eq(data["previous_shares"]),
        ],
        ["new", "increased", "decreased", "unchanged"],
        default="unknown",
    )
    return data.drop(columns=["report_period_sort"], errors="ignore").reset_index(drop=True)


def score_sponsorship_row(row: pd.Series) -> float:
    score = 0.0
    score += min(float(row.get("passive_giant_count", 0)), 5.0) * 0.5
    score += min(float(row.get("active_signal_rich_count", 0)), 3.0) * 2.0
    score += min(float(row.get("bank_broker_complex_count", 0)), 5.0) * 0.2
    score += min(float(row.get("weighted_holder_score", 0)), 5.0)
    return round(score, 2)


def build_gold_tables(holdings: pd.DataFrame, output_dir: Path) -> dict[str, pd.DataFrame]:
    latest = build_latest_holdings(holdings)
    sponsorship = build_ticker_sponsorship(latest)
    deltas = build_position_deltas(holdings)
    tables = {
        "latest_holdings": latest,
        "ticker_sponsorship": sponsorship,
        "position_deltas": deltas,
    }
    for table_name, data in tables.items():
        TableStore(output_dir, table_name).replace(data)
    return tables


def _build_manager_type_counts(data: pd.DataFrame) -> pd.DataFrame:
    if "manager_type" not in data.columns:
        type_counts = pd.DataFrame({"ticker": sorted(data["ticker"].unique())})
    else:
        type_counts = (
            data.pivot_table(
                index="ticker",
                columns="manager_type",
                values="institution_cik",
                aggfunc=pd.Series.nunique,
                fill_value=0,
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )

    for manager_type in ManagerType:
        if manager_type.value not in type_counts.columns:
            type_counts[manager_type.value] = 0

    return type_counts


def _build_holder_flags(data: pd.DataFrame) -> pd.DataFrame:
    flags = pd.DataFrame({"ticker": sorted(data["ticker"].unique())})
    if "institution_name" not in data.columns:
        for column in ["has_blackrock", "has_vanguard", "has_state_street", "has_berkshire"]:
            flags[column] = False
        return flags

    for name, column in {
        "BlackRock": "has_blackrock",
        "Vanguard": "has_vanguard",
        "State Street": "has_state_street",
        "Berkshire Hathaway": "has_berkshire",
    }.items():
        owned = set(data.loc[data["institution_name"].eq(name), "ticker"])
        flags[column] = flags["ticker"].isin(owned)
    return flags


def _ensure_count_columns(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    for column in [
        "passive_giant_count",
        "active_signal_rich_count",
        "bank_broker_complex_count",
        "total_institution_count",
    ]:
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    return result


def _safe_pct_delta(current: pd.Series, previous: pd.Series) -> pd.Series:
    previous_clean = previous.replace({0: np.nan})
    return ((current - previous_clean) / previous_clean) * 100.0

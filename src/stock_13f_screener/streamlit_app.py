from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import streamlit as st

from stock_13f_screener.config import get_settings
from stock_13f_screener.parquet_store import TableStore

DEFAULT_DISPLAY_ROWS = 5_000
MAX_DISPLAY_ROWS = 50_000
DASHBOARD_PREVIEW_ROWS = 50
SPECIAL_TICKER_PATTERN = r"[A-Z0-9.\-]+"

PAGE_NAMES = [
    "Dashboard",
    "Research Leads",
    "Holdings",
    "Ticker Sponsorship",
    "Position Deltas",
    "Mapping Diagnostics",
]

SPONSORSHIP_SORT_COLUMNS = [
    "institutional_signal_score",
    "weighted_holder_score",
    "log_total_value_usd_thousands",
    "total_institution_count",
    "ticker",
]

RESEARCH_LEAD_COLUMNS = [
    "ticker",
    "institutional_signal_score",
    "weighted_holder_score",
    "log_total_value_usd_thousands",
    "total_value_usd_thousands",
    "total_institution_count",
    "passive_giant_count",
    "active_signal_rich_count",
    "bank_broker_complex_count",
    "has_blackrock",
    "has_vanguard",
    "has_state_street",
    "has_berkshire",
    "is_special_ticker",
]


@dataclass(frozen=True)
class CommonFilters:
    manager_types: list[str]
    ticker_query: str
    institution_query: str
    min_value_usd_thousands: float | None


@dataclass(frozen=True)
class SponsorshipFilters:
    min_active_holders: int
    min_passive_holders: int
    min_signal_score: float
    ticker_query: str
    show_special_only: bool
    min_log_value: float | None


@dataclass(frozen=True)
class MappingFilters:
    unresolved_only: bool
    statuses: list[str]
    ticker_query: str


PageRenderer = Callable[[Path], None]


def main() -> None:
    st.set_page_config(page_title="13F Institutional Screener", layout="wide")
    st.title("13F Institutional Holdings Screener")
    st.caption("Delayed SEC 13F data. Research filter, not buy/sell advice.")

    data_dir = get_data_dir_from_sidebar()
    page = st.sidebar.radio("Page", PAGE_NAMES)
    get_page_renderers()[page](data_dir)


def get_page_renderers() -> dict[str, PageRenderer]:
    return {
        "Dashboard": render_dashboard,
        "Research Leads": render_research_leads,
        "Holdings": render_holdings,
        "Ticker Sponsorship": render_sponsorship,
        "Position Deltas": render_deltas,
        "Mapping Diagnostics": render_mapping_diagnostics,
    }


def get_data_dir_from_sidebar() -> Path:
    settings = get_settings()
    return Path(st.sidebar.text_input("Data directory", str(settings.data_dir)))


def render_dashboard(data_dir: Path) -> None:
    latest = load_table(data_dir / "gold", "latest_holdings")
    sponsorship = load_sponsorship_table(data_dir)
    mapping = load_table(data_dir / "silver", "cusip_map")

    render_dashboard_metrics(latest, sponsorship, mapping)

    if sponsorship.empty:
        st.info("No gold tables found. Run `stock13f make-example-data --output-dir data` first.")
        return

    show_score_health(sponsorship)
    st.subheader("Top institutional research leads")
    st.dataframe(sort_sponsorship(sponsorship).head(DASHBOARD_PREVIEW_ROWS), width="stretch")


def render_dashboard_metrics(
    latest: pd.DataFrame,
    sponsorship: pd.DataFrame,
    mapping: pd.DataFrame,
) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest holdings", f"{len(latest):,}")
    col2.metric("Tickers", format_unique_count(sponsorship, "ticker"))

    resolved, total = get_mapping_resolution_counts(mapping)
    if total:
        col3.metric("CUSIP match rate", f"{resolved / total:.1%}")
        col4.metric("Unresolved CUSIPs", f"{total - resolved:,}")
        return

    col3.metric("CUSIP match rate", "n/a")
    col4.metric("Unresolved CUSIPs", "n/a")


def render_research_leads(data_dir: Path) -> None:
    data = load_sponsorship_table(data_dir)
    st.subheader("Research Leads")
    st.caption(
        "Composite score plus deterministic tie-breakers. Use as triage, not trading advice."
    )

    if data.empty:
        st.info("No sponsorship table found.")
        return

    filtered = apply_sponsorship_filters(
        data,
        render_sponsorship_filter_controls(data, key_prefix="research", show_advanced=True),
    )
    filtered = select_existing_columns(sort_sponsorship(filtered), RESEARCH_LEAD_COLUMNS)
    render_limited_dataframe(filtered, label="Research leads")
    render_download_button(filtered, "research_leads.csv")


def render_holdings(data_dir: Path) -> None:
    data = load_table(data_dir / "gold", "latest_holdings")
    render_common_table_page(
        data=data,
        title="Latest Holdings",
        label="Latest holdings",
        key_prefix="holdings",
        filename="latest_holdings_filtered.csv",
        sort_columns=["value_usd_thousands"],
        ascending=False,
    )


def render_sponsorship(data_dir: Path) -> None:
    data = load_sponsorship_table(data_dir)
    st.subheader("Ticker Sponsorship")

    if data.empty:
        st.info("No sponsorship table found.")
        return

    filtered = apply_sponsorship_filters(
        data,
        render_sponsorship_filter_controls(data, key_prefix="sponsorship", show_advanced=True),
    )
    filtered = sort_sponsorship(filtered)
    render_limited_dataframe(filtered, label="Ticker sponsorship")
    render_download_button(filtered, "ticker_sponsorship_filtered.csv")


def render_deltas(data_dir: Path) -> None:
    data = load_table(data_dir / "gold", "position_deltas")
    st.subheader("Position Deltas")

    if data.empty:
        st.info("No deltas table found.")
        return

    filtered = apply_delta_status_filter(data)
    filtered = apply_common_filters(
        filtered,
        render_common_filter_controls(filtered, key_prefix="deltas"),
    )
    filtered = sort_deltas(filtered)
    render_limited_dataframe(filtered, label="Position deltas")
    render_download_button(filtered, "position_deltas_filtered.csv")


def render_mapping_diagnostics(data_dir: Path) -> None:
    mapping = load_table(data_dir / "silver", "cusip_map")
    st.subheader("CUSIP Mapping Diagnostics")

    if mapping.empty:
        st.info("No CUSIP mapping cache found.")
        return

    mapping = clean_index_columns(mapping)
    render_mapping_metrics(mapping)
    filters = render_mapping_filter_controls(mapping)
    filtered = apply_mapping_filters(mapping, filters)
    render_limited_dataframe(filtered, label="CUSIP mapping diagnostics")
    render_download_button(filtered, "cusip_mapping_diagnostics.csv")


def render_common_table_page(
    *,
    data: pd.DataFrame,
    title: str,
    label: str,
    key_prefix: str,
    filename: str,
    sort_columns: list[str],
    ascending: bool,
) -> None:
    st.subheader(title)

    if data.empty:
        st.info(f"No {label.lower()} table found.")
        return

    filters = render_common_filter_controls(data, key_prefix=key_prefix)
    filtered = apply_common_filters(data, filters)
    filtered = sort_if_present(filtered, sort_columns, ascending=ascending)
    render_limited_dataframe(filtered, label=label)
    render_download_button(filtered, filename)


def render_common_filter_controls(data: pd.DataFrame, *, key_prefix: str) -> CommonFilters:
    return CommonFilters(
        manager_types=select_manager_types(data, key_prefix=key_prefix),
        ticker_query=read_text_filter("Ticker contains", key=f"{key_prefix}_ticker", upper=True),
        institution_query=read_text_filter(
            "Institution contains",
            key=f"{key_prefix}_institution",
            enabled="institution_name" in data.columns,
        ),
        min_value_usd_thousands=read_min_value_filter(data, key_prefix=key_prefix),
    )


def apply_common_filters(data: pd.DataFrame, filters: CommonFilters) -> pd.DataFrame:
    filtered = data.copy()
    filtered = filter_by_allowed_values(filtered, "manager_type", filters.manager_types)
    filtered = filter_by_text_contains(filtered, "ticker", filters.ticker_query, uppercase=True)
    filtered = filter_by_text_contains(filtered, "institution_name", filters.institution_query)
    filtered = filter_by_min_numeric(
        filtered,
        "value_usd_thousands",
        filters.min_value_usd_thousands,
    )
    return filtered


def render_sponsorship_filter_controls(
    data: pd.DataFrame,
    *,
    key_prefix: str,
    show_advanced: bool,
) -> SponsorshipFilters:
    col1, col2, col3 = st.columns(3)
    base_filters = SponsorshipFilters(
        min_active_holders=col1.slider(
            "Minimum active/signal-rich holders",
            0,
            10,
            0,
            key=f"{key_prefix}_min_active",
        ),
        min_passive_holders=col2.slider(
            "Minimum passive giant holders",
            0,
            10,
            0,
            key=f"{key_prefix}_min_passive",
        ),
        min_signal_score=col3.number_input(
            "Minimum institutional signal score",
            value=0.0,
            key=f"{key_prefix}_min_score",
        ),
        ticker_query=read_text_filter(
            "Ticker contains",
            key=f"{key_prefix}_ticker",
            upper=True,
        ),
        show_special_only=False,
        min_log_value=None,
    )

    if not show_advanced:
        return base_filters

    return render_advanced_sponsorship_filters(data, base_filters, key_prefix=key_prefix)


def render_advanced_sponsorship_filters(
    data: pd.DataFrame,
    base_filters: SponsorshipFilters,
    *,
    key_prefix: str,
) -> SponsorshipFilters:
    with st.expander("Advanced filters"):
        return SponsorshipFilters(
            min_active_holders=base_filters.min_active_holders,
            min_passive_holders=base_filters.min_passive_holders,
            min_signal_score=base_filters.min_signal_score,
            ticker_query=base_filters.ticker_query,
            show_special_only=st.checkbox(
                "Special tickers only",
                value=False,
                key=f"{key_prefix}_special_only",
            ),
            min_log_value=st.slider(
                "Minimum log1p(total value, USD thousands)",
                min_value=0.0,
                max_value=get_numeric_max(data, "log_total_value_usd_thousands", default=1.0),
                value=0.0,
                key=f"{key_prefix}_min_log_value",
            ),
        )


def apply_sponsorship_filters(
    data: pd.DataFrame,
    filters: SponsorshipFilters,
) -> pd.DataFrame:
    filtered = data.copy()
    filtered = filter_by_min_numeric(
        filtered,
        "active_signal_rich_count",
        filters.min_active_holders,
    )
    filtered = filter_by_min_numeric(
        filtered,
        "passive_giant_count",
        filters.min_passive_holders,
    )
    filtered = filter_by_min_numeric(
        filtered,
        "institutional_signal_score",
        filters.min_signal_score,
    )
    filtered = filter_by_text_contains(filtered, "ticker", filters.ticker_query, uppercase=True)
    filtered = filter_by_special_ticker(filtered, filters.show_special_only)
    filtered = filter_by_min_numeric(filtered, "log_total_value_usd_thousands", filters.min_log_value)
    return filtered


def render_mapping_metrics(mapping: pd.DataFrame) -> None:
    resolved, total = get_mapping_resolution_counts(mapping)
    col1, col2, col3 = st.columns(3)
    col1.metric("CUSIPs", f"{total:,}")
    col2.metric("Resolved", f"{resolved:,}")
    col3.metric("Match rate", f"{resolved / total:.1%}" if total else "0.0%")


def render_mapping_filter_controls(mapping: pd.DataFrame) -> MappingFilters:
    return MappingFilters(
        unresolved_only=st.checkbox("Show unresolved only", value=True),
        statuses=select_mapping_statuses(mapping),
        ticker_query=read_text_filter("Ticker contains", key="mapping_ticker", upper=True),
    )


def apply_mapping_filters(mapping: pd.DataFrame, filters: MappingFilters) -> pd.DataFrame:
    filtered = mapping.copy()

    if filters.unresolved_only:
        filtered = filter_unresolved_mappings(filtered)

    filtered = filter_by_allowed_values(filtered, "status", filters.statuses)
    return filter_by_text_contains(filtered, "ticker", filters.ticker_query, uppercase=True)


def select_manager_types(data: pd.DataFrame, *, key_prefix: str) -> list[str]:
    if "manager_type" not in data.columns:
        return []

    manager_types = sorted(data["manager_type"].dropna().unique())
    return st.multiselect(
        "Manager type",
        manager_types,
        default=manager_types,
        key=f"{key_prefix}_manager_type",
    )


def select_mapping_statuses(mapping: pd.DataFrame) -> list[str]:
    if "status" not in mapping.columns:
        return []

    statuses = sorted(mapping["status"].dropna().unique())
    return st.multiselect("Status", statuses, default=statuses, key="mapping_status")


def read_text_filter(
    label: str,
    *,
    key: str,
    upper: bool = False,
    enabled: bool = True,
) -> str:
    if not enabled:
        return ""

    value = st.text_input(label, "", key=key).strip()
    return value.upper() if upper else value


def read_min_value_filter(data: pd.DataFrame, *, key_prefix: str) -> float | None:
    if "value_usd_thousands" not in data.columns:
        return None

    return st.number_input(
        "Minimum value, USD thousands",
        min_value=0.0,
        value=0.0,
        key=f"{key_prefix}_min_value",
    )


def apply_delta_status_filter(data: pd.DataFrame) -> pd.DataFrame:
    if "position_status" not in data.columns:
        return data.copy()

    statuses = sorted(data["position_status"].dropna().unique())
    selected = st.multiselect("Status", statuses, default=statuses, key="deltas_status")
    return filter_by_allowed_values(data, "position_status", selected)


def filter_by_allowed_values(
    data: pd.DataFrame,
    column: str,
    allowed_values: list[str],
) -> pd.DataFrame:
    if column not in data.columns or not allowed_values:
        return data
    return data[data[column].isin(allowed_values)]


def filter_by_text_contains(
    data: pd.DataFrame,
    column: str,
    query: str,
    *,
    uppercase: bool = False,
) -> pd.DataFrame:
    if column not in data.columns or not query:
        return data

    series = data[column].astype(str)
    if uppercase:
        series = series.str.upper()
    return data[series.str.contains(query, case=not uppercase, na=False)]


def filter_by_min_numeric(
    data: pd.DataFrame,
    column: str,
    minimum: float | int | None,
) -> pd.DataFrame:
    if column not in data.columns or minimum is None:
        return data

    values = pd.to_numeric(data[column], errors="coerce").fillna(0)
    return data[values.ge(minimum)]


def filter_by_special_ticker(data: pd.DataFrame, show_special_only: bool) -> pd.DataFrame:
    if not show_special_only or "is_special_ticker" not in data.columns:
        return data
    return data[data["is_special_ticker"]]


def filter_unresolved_mappings(mapping: pd.DataFrame) -> pd.DataFrame:
    if "status" not in mapping.columns:
        return mapping
    return mapping[mapping["status"].ne("resolved")]


def render_limited_dataframe(
    data: pd.DataFrame,
    *,
    label: str,
    default_limit: int = DEFAULT_DISPLAY_ROWS,
    max_limit: int = MAX_DISPLAY_ROWS,
) -> None:
    row_count = len(data)

    if row_count == 0:
        st.info(f"No rows match current filters for {label}.")
        return

    limit = render_row_limit_control(row_count, label, default_limit, max_limit)
    warn_if_limited(row_count, limit)
    st.dataframe(data.head(limit), width="stretch")


def render_row_limit_control(
    row_count: int,
    label: str,
    default_limit: int,
    max_limit: int,
) -> int:
    max_safe_limit = max(100, min(max_limit, row_count))
    default_safe_limit = max(100, min(default_limit, max_safe_limit))

    col1, col2 = st.columns([2, 1])
    col1.caption(f"{label}: {row_count:,} rows after filters")
    return int(
        col2.number_input(
            "Rows to display",
            min_value=100,
            max_value=max_safe_limit,
            value=default_safe_limit,
            step=100,
            key=f"{label}_row_limit",
        )
    )


def warn_if_limited(row_count: int, limit: int) -> None:
    if row_count <= limit:
        return

    st.warning(
        f"Showing first {limit:,} of {row_count:,} rows. "
        "Narrow filters to inspect more precisely."
    )


def render_download_button(data: pd.DataFrame, filename: str) -> None:
    if data.empty:
        return
    st.download_button(
        "Download filtered CSV",
        data=data.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
    )


def show_score_health(data: pd.DataFrame) -> None:
    if "institutional_signal_score" not in data.columns:
        return

    saturation_rate = get_top_value_rate(data["institutional_signal_score"])
    if saturation_rate < 0.25:
        return

    st.warning(
        "Score saturation detected: "
        f"{saturation_rate:.1%} of tickers share the most common score. "
        "Tables use tie-breakers: weighted score, log value, institution count, ticker."
    )


def load_sponsorship_table(data_dir: Path) -> pd.DataFrame:
    return prepare_sponsorship_frame(load_table(data_dir / "gold", "ticker_sponsorship"))


def prepare_sponsorship_frame(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data.copy()

    result = clean_index_columns(data)
    result = add_ticker_quality_columns(result)
    result = add_log_value_column(result)
    return add_rank_sort_score(result)


def clean_index_columns(data: pd.DataFrame) -> pd.DataFrame:
    return data.drop(columns=["Unnamed: 0"], errors="ignore").copy()


def add_ticker_quality_columns(data: pd.DataFrame) -> pd.DataFrame:
    if "ticker" not in data.columns or "ticker_raw" in data.columns:
        return data

    result = data.copy()
    result["ticker_raw"] = result["ticker"].astype("string")
    result["ticker_display"] = result["ticker_raw"]
    result["is_special_ticker"] = ~result["ticker_raw"].str.fullmatch(
        SPECIAL_TICKER_PATTERN,
        na=False,
    )
    return result


def add_log_value_column(data: pd.DataFrame) -> pd.DataFrame:
    if "total_value_usd_thousands" not in data.columns:
        return data
    if "log_total_value_usd_thousands" in data.columns:
        return data

    result = data.copy()
    values = pd.to_numeric(result["total_value_usd_thousands"], errors="coerce").fillna(0)
    result["log_total_value_usd_thousands"] = np.log1p(values.clip(lower=0))
    return result


def add_rank_sort_score(data: pd.DataFrame) -> pd.DataFrame:
    if "rank_sort_score" in data.columns:
        return data

    result = data.copy()
    result["rank_sort_score"] = (
        numeric_column(result, "institutional_signal_score") * 1_000_000
        + numeric_column(result, "weighted_holder_score") * 10_000
        + numeric_column(result, "log_total_value_usd_thousands") * 100
        + numeric_column(result, "total_institution_count")
    )
    return result


def sort_sponsorship(data: pd.DataFrame) -> pd.DataFrame:
    sort_columns = [column for column in SPONSORSHIP_SORT_COLUMNS if column in data.columns]
    if not sort_columns:
        return data

    ascending = [column == "ticker" for column in sort_columns]
    return data.sort_values(sort_columns, ascending=ascending)


def sort_deltas(data: pd.DataFrame) -> pd.DataFrame:
    if "value_delta" not in data.columns:
        return data

    return data.assign(abs_value_delta=data["value_delta"].fillna(0).abs()).sort_values(
        "abs_value_delta",
        ascending=False,
    )


def sort_if_present(data: pd.DataFrame, columns: list[str], *, ascending: bool) -> pd.DataFrame:
    sort_columns = [column for column in columns if column in data.columns]
    if not sort_columns:
        return data
    return data.sort_values(sort_columns, ascending=ascending)


def select_existing_columns(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    existing_columns = [column for column in columns if column in data.columns]
    return data[existing_columns].copy() if existing_columns else data


def format_unique_count(data: pd.DataFrame, column: str) -> str:
    if column not in data.columns:
        return "0"
    return f"{data[column].nunique():,}"


def get_mapping_resolution_counts(mapping: pd.DataFrame) -> tuple[int, int]:
    if mapping.empty or "status" not in mapping.columns:
        return 0, 0
    return int(mapping["status"].eq("resolved").sum()), len(mapping)


def get_numeric_max(data: pd.DataFrame, column: str, *, default: float) -> float:
    if column not in data.columns or data.empty:
        return default

    value = pd.to_numeric(data[column], errors="coerce").max()
    return default if pd.isna(value) else max(default, float(value))


def numeric_column(data: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(data.get(column, pd.Series(0, index=data.index)), errors="coerce").fillna(0)


def get_top_value_rate(series: pd.Series) -> float:
    counts = series.value_counts(dropna=False)
    if counts.empty:
        return 0.0
    return int(counts.iloc[0]) / len(series)


@st.cache_data(show_spinner=False)
def load_table(layer_dir: Path, table_name: str) -> pd.DataFrame:
    return TableStore(layer_dir, table_name).read()

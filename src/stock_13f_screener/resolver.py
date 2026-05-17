from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from loguru import logger

from stock_13f_screener.cusip import safe_normalize_cusip
from stock_13f_screener.openfigi_client import OpenFigiClient, OpenFigiMapping
from stock_13f_screener.parquet_store import TableStore

CUSIP_MAP_COLUMNS = [
    "cusip",
    "ticker",
    "figi",
    "composite_figi",
    "share_class_figi",
    "name",
    "exchange_code",
    "market_sector",
    "security_type",
    "security_type_2",
    "raw_rank",
    "status",
    "error",
    "source",
    "resolved_at",
]


class CusipResolver:
    """Cache-first CUSIP resolver."""

    def __init__(self, cache_dir: Path, openfigi_client: OpenFigiClient | None = None) -> None:
        self.store = TableStore(cache_dir, "cusip_map")
        self.openfigi_client = openfigi_client or OpenFigiClient()

    def resolve(self, cusips: list[str]) -> pd.DataFrame:
        normalized = sorted({value for raw in cusips if (value := safe_normalize_cusip(raw))})
        cache = self._load_cache()
        cached_cusips = set(cache["cusip"]) if not cache.empty else set()
        missing = [cusip for cusip in normalized if cusip not in cached_cusips]
        logger.info(
            "CUSIP resolver requested={} cached={} missing={}",
            len(normalized),
            len(normalized) - len(missing),
            len(missing),
        )
        if missing:
            fetched = self._fetch(missing)
            cache = self.store.append_upsert(fetched, keys=["cusip"])
        return cache[cache["cusip"].isin(normalized)].copy()

    def _load_cache(self) -> pd.DataFrame:
        cache = self.store.read()
        if cache.empty:
            return pd.DataFrame(columns=CUSIP_MAP_COLUMNS)
        for column in CUSIP_MAP_COLUMNS:
            if column not in cache.columns:
                cache[column] = None
        return cache[CUSIP_MAP_COLUMNS]

    def _fetch(self, cusips: list[str]) -> pd.DataFrame:
        mappings = self.openfigi_client.map_cusips(cusips)
        resolved_at = datetime.now(UTC).isoformat()
        rows = [
            self._mapping_to_row(cusip, mapping, resolved_at) for cusip, mapping in mappings.items()
        ]
        return pd.DataFrame(rows, columns=CUSIP_MAP_COLUMNS)

    @staticmethod
    def _mapping_to_row(
        cusip: str, mapping: OpenFigiMapping, resolved_at: str
    ) -> dict[str, object]:
        row = asdict(mapping)
        return {
            "cusip": cusip,
            "ticker": row["ticker"],
            "figi": row["figi"],
            "composite_figi": row["composite_figi"],
            "share_class_figi": row["share_class_figi"],
            "name": row["name"],
            "exchange_code": row["exchange_code"],
            "market_sector": row["market_sector"],
            "security_type": row["security_type"],
            "security_type_2": row["security_type_2"],
            "raw_rank": row["raw_rank"],
            "status": row["status"],
            "error": row["error"],
            "source": "openfigi",
            "resolved_at": resolved_at,
        }


def attach_tickers_to_holdings(holdings: pd.DataFrame, cache_dir: Path) -> pd.DataFrame:
    if "cusip" not in holdings.columns:
        raise ValueError("holdings must include cusip column")
    resolver = CusipResolver(cache_dir=cache_dir)
    unique_cusips = holdings["cusip"].dropna().astype(str).unique().tolist()
    mapping = resolver.resolve(unique_cusips)
    resolved = holdings.merge(mapping, how="left", on="cusip", validate="many_to_one")
    resolved["is_resolved"] = resolved["ticker"].notna()
    return resolved

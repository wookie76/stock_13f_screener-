from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable

import requests
from loguru import logger
from pydantic import BaseModel, Field

from stock_13f_screener.cusip import normalize_cusip
from stock_13f_screener.fetch_policy import RespectfulFetchPolicy

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"


class OpenFigiConfig(BaseModel):
    api_key: str | None = Field(default_factory=lambda: os.getenv("OPENFIGI_API_KEY") or None)
    timeout_seconds: float = 30.0
    max_retries: int = 5
    jobs_per_request_no_key: int = 10
    jobs_per_request_with_key: int = 100
    sleep_no_key_seconds: float = 2.7
    sleep_with_key_seconds: float = 0.30
    jitter_min_seconds: float = 0.10
    jitter_max_seconds: float = 0.75


@dataclass(frozen=True)
class OpenFigiMapping:
    input_cusip: str
    ticker: str | None
    figi: str | None
    composite_figi: str | None
    share_class_figi: str | None
    name: str | None
    exchange_code: str | None
    market_sector: str | None
    security_type: str | None
    security_type_2: str | None
    raw_rank: int
    status: str
    error: str | None = None


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for index in range(0, len(values), size):
        yield values[index : index + size]


class OpenFigiClient:
    """Cache-layer-friendly OpenFIGI batch client."""

    def __init__(self, config: OpenFigiConfig | None = None) -> None:
        self.config = config or OpenFigiConfig()
        self.session = requests.Session()
        self.policy = RespectfulFetchPolicy(
            base_sleep_seconds=self.base_sleep_seconds,
            jitter_min_seconds=self.config.jitter_min_seconds,
            jitter_max_seconds=self.config.jitter_max_seconds,
        )

    @property
    def jobs_per_request(self) -> int:
        return (
            self.config.jobs_per_request_with_key
            if self.config.api_key
            else self.config.jobs_per_request_no_key
        )

    @property
    def base_sleep_seconds(self) -> float:
        return (
            self.config.sleep_with_key_seconds
            if self.config.api_key
            else self.config.sleep_no_key_seconds
        )

    def map_cusips(self, cusips: list[str]) -> dict[str, OpenFigiMapping]:
        normalized = sorted({normalize_cusip(cusip) for cusip in cusips})
        results: dict[str, OpenFigiMapping] = {}
        for batch in chunked(normalized, self.jobs_per_request):
            logger.info("OpenFIGI mapping batch size={}", len(batch))
            results.update(self._map_batch(batch))
            self.policy.sleep("OpenFIGI")
        return results

    def _map_batch(self, cusips: list[str]) -> dict[str, OpenFigiMapping]:
        payload = [{"idType": "ID_CUSIP", "idValue": cusip} for cusip in cusips]
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.config.api_key
        response_json = self._post_with_retries(payload, headers)
        if len(response_json) != len(cusips):
            raise RuntimeError(
                f"OpenFIGI response length mismatch: {len(response_json)} for {len(cusips)}"
            )
        return {
            cusip: self._parse_response_item(cusip, item)
            for cusip, item in zip(cusips, response_json, strict=True)
        }

    def _post_with_retries(
        self,
        payload: list[dict[str, str]],
        headers: dict[str, str],
    ) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.session.post(
                    OPENFIGI_MAPPING_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    self.policy.backoff_sleep("OpenFIGI", attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list):
                    raise RuntimeError("OpenFIGI response must be a list")
                return data
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
                self.policy.backoff_sleep("OpenFIGI", attempt)
        raise RuntimeError("OpenFIGI request failed after retries") from last_error

    def _parse_response_item(self, cusip: str, response_item: dict[str, Any]) -> OpenFigiMapping:
        if "error" in response_item:
            return self._empty(cusip, str(response_item["error"]))
        rows = response_item.get("data", [])
        if not rows:
            return self._empty(cusip, "No OpenFIGI data returned")
        ranked_rows = sorted(
            enumerate(rows),
            key=lambda pair: self._rank_mapping_row(pair[1]),
            reverse=True,
        )
        raw_rank, best = ranked_rows[0]
        return OpenFigiMapping(
            input_cusip=cusip,
            ticker=best.get("ticker"),
            figi=best.get("figi"),
            composite_figi=best.get("compositeFIGI"),
            share_class_figi=best.get("shareClassFIGI"),
            name=best.get("name"),
            exchange_code=best.get("exchCode"),
            market_sector=best.get("marketSector") or best.get("marketSecDes"),
            security_type=best.get("securityType"),
            security_type_2=best.get("securityType2"),
            raw_rank=raw_rank,
            status="resolved" if best.get("ticker") else "missing_ticker",
        )

    @staticmethod
    def _empty(cusip: str, error: str) -> OpenFigiMapping:
        return OpenFigiMapping(
            input_cusip=cusip,
            ticker=None,
            figi=None,
            composite_figi=None,
            share_class_figi=None,
            name=None,
            exchange_code=None,
            market_sector=None,
            security_type=None,
            security_type_2=None,
            raw_rank=-1,
            status="unresolved",
            error=error,
        )

    @staticmethod
    def _rank_mapping_row(row: dict[str, Any]) -> tuple[int, int, int, int]:
        market_sector = str(row.get("marketSector") or row.get("marketSecDes") or "").lower()
        security_type = str(row.get("securityType") or "").lower()
        security_type_2 = str(row.get("securityType2") or "").lower()
        is_equity = market_sector == "equity"
        is_common_like = (
            "common" in security_type
            or "common" in security_type_2
            or security_type in {"etp", "etf"}
            or security_type_2 in {"etp", "etf"}
        )
        return (
            int(is_equity),
            int(is_common_like),
            int(bool(row.get("ticker"))),
            int(bool(row.get("exchCode"))),
        )

from __future__ import annotations

from pathlib import Path

from loguru import logger
from tqdm import tqdm

from stock_13f_screener.fetch_policy import RespectfulFetchPolicy
from stock_13f_screener.managers import Institution, select_institutions


def download_13f_filings(
    institutions: list[Institution] | None,
    output_dir: Path,
    company_name: str,
    email: str,
    limit: int = 1,
    include_amends: bool = False,
    sleep_seconds: float = 0.25,
) -> int:
    """Download 13F-HR filings to disk using sec-edgar-downloader."""
    from sec_edgar_downloader import Downloader

    selected = institutions or select_institutions()
    output_dir.mkdir(parents=True, exist_ok=True)
    dl = Downloader(company_name, email, str(output_dir))
    policy = RespectfulFetchPolicy(base_sleep_seconds=sleep_seconds)
    total_downloaded = 0

    for institution in tqdm(selected, desc="Downloading 13F-HR"):
        logger.info("Downloading {} CIK={} limit={}", institution.name, institution.cik, limit)
        downloaded = dl.get("13F-HR", institution.cik, limit=limit, include_amends=include_amends)
        total_downloaded += int(downloaded)
        policy.sleep("SEC EDGAR")

    logger.info("Downloaded {} filing(s)", total_downloaded)
    return total_downloaded

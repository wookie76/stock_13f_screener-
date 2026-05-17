from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from stock_13f_screener.analytics import build_gold_tables
from stock_13f_screener.config import get_settings
from stock_13f_screener.example_data import make_example_data
from stock_13f_screener.logging_setup import configure_logging
from stock_13f_screener.managers import INSTITUTIONS, select_institutions
from stock_13f_screener.parquet_store import TableStore
from stock_13f_screener.parse_13f import parse_filings_tree
from stock_13f_screener.resolver import attach_tickers_to_holdings
from stock_13f_screener.sec_download import download_13f_filings

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.callback()
def _main(log_level: Annotated[str, typer.Option(help="Log level.")] = "INFO") -> None:
    configure_logging(log_level)


@app.command()
def list_institutions() -> None:
    """Show built-in institution registry."""
    table = Table(title="Institution Registry")
    table.add_column("Name")
    table.add_column("CIK")
    table.add_column("Type")
    table.add_column("Weight", justify="right")
    for institution in INSTITUTIONS.values():
        table.add_row(
            institution.name,
            institution.cik,
            institution.manager_type.value,
            f"{institution.signal_weight:.2f}",
        )
    console.print(table)


@app.command()
def download(
    names: Annotated[
        list[str] | None, typer.Option("--name", help="Institution name. Repeatable.")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, help="Filings per institution.")] = 1,
    data_dir: Annotated[Path | None, typer.Option(help="Data directory.")] = None,
    include_amends: Annotated[bool, typer.Option(help="Include amended filings.")] = False,
) -> None:
    """Download 13F-HR filings for built-in institutions."""
    settings = get_settings()
    root = data_dir or settings.data_dir
    institutions = select_institutions(names)
    downloaded = download_13f_filings(
        institutions=institutions,
        output_dir=root / "raw" / "sec_filings",
        company_name=settings.sec_company_name,
        email=settings.sec_email,
        limit=limit,
        include_amends=include_amends,
        sleep_seconds=1.0 / settings.sec_requests_per_second,
    )
    logger.info("Downloaded filing count={}", downloaded)


@app.command()
def parse(
    raw_dir: Annotated[Path | None, typer.Option(help="Raw SEC download directory.")] = None,
    output_path: Annotated[Path | None, typer.Option(help="Output parquet path.")] = None,
) -> None:
    """Parse downloaded 13F-HR filings into holdings parquet."""
    settings = get_settings()
    raw = raw_dir or settings.raw_dir
    output = output_path or settings.silver_dir / "holdings.parquet"
    data = parse_filings_tree(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(output, index=False)
    logger.info("Parsed holdings rows={} output={}", len(data), output)


@app.command("resolve-cusips")
def resolve_cusips(
    holdings_path: Annotated[Path, typer.Option(exists=True, readable=True)],
    cache_dir: Annotated[Path | None, typer.Option(help="Directory for cusip_map table.")] = None,
    output_path: Annotated[
        Path | None, typer.Option(help="Resolved holdings parquet path.")
    ] = None,
) -> None:
    """Resolve CUSIPs using cache-first OpenFIGI lookup."""
    settings = get_settings()
    cache_root = cache_dir or settings.silver_dir
    output = output_path or settings.silver_dir / "holdings_resolved.parquet"
    holdings = pd.read_parquet(holdings_path)
    resolved = attach_tickers_to_holdings(holdings, cache_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    resolved.to_parquet(output, index=False)
    total = len(resolved)
    matched = int(resolved["is_resolved"].sum()) if total else 0
    logger.info(
        "Resolved rows={} matched={} match_rate={:.2%}",
        total,
        matched,
        matched / total if total else 0,
    )
    logger.info("Resolved holdings output={}", output)


@app.command("build-gold")
def build_gold(
    holdings_path: Annotated[Path, typer.Option(exists=True, readable=True)],
    output_dir: Annotated[Path | None, typer.Option(help="Gold output directory.")] = None,
) -> None:
    """Build gold analytical tables."""
    settings = get_settings()
    output = output_dir or settings.gold_dir
    holdings = pd.read_parquet(holdings_path)
    tables = build_gold_tables(holdings, output)
    for name, data in tables.items():
        logger.info("Gold table {} rows={}", name, len(data))


@app.command("make-example-data")
def make_examples(
    output_dir: Annotated[Path | None, typer.Option(help="Data root.")] = None,
) -> None:
    """Create no-network example tables for Streamlit smoke tests."""
    settings = get_settings()
    paths = make_example_data(output_dir or settings.data_dir)
    for name, path in paths.items():
        logger.info("Created {}: {}", name, path)


@app.command("show-table")
def show_table(
    table_name: Annotated[str, typer.Argument(help="Table name under a data layer.")],
    layer_dir: Annotated[
        Path, typer.Option(help="Layer dir, e.g. data/gold or data/silver.")
    ] = Path("data/gold"),
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
) -> None:
    """Preview a stored table."""
    data = TableStore(layer_dir, table_name).read().head(limit)
    console.print(data)

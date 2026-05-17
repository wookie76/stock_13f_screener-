from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from pydantic import ValidationError

from stock_13f_screener.cusip import safe_normalize_cusip
from stock_13f_screener.managers import Institution, institution_by_cik
from stock_13f_screener.models import HoldingRow

_TAG_MAP = {
    "nameofissuer": "issuer_name",
    "titleofclass": "class_title",
    "cusip": "cusip",
    "value": "value_usd_thousands",
    "sshprnamt": "shares",
    "sshprnamttype": "share_type",
    "putcall": "put_call",
    "investmentdiscretion": "investment_discretion",
    "sole": "voting_sole",
    "shared": "voting_shared",
    "none": "voting_none",
}

_NUMERIC_COLUMNS = ["value_usd_thousands", "shares", "voting_sole", "voting_shared", "voting_none"]


def parse_filings_tree(raw_dir: Path) -> pd.DataFrame:
    files = discover_filing_files(raw_dir)
    rows: list[dict[str, object]] = []
    for file_path in files:
        rows.extend(parse_filing_file(file_path))
    data = pd.DataFrame(rows)
    if data.empty:
        return data
    return clean_holdings_frame(data)


def discover_filing_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw SEC directory does not exist: {raw_dir}")
    candidates = [path for path in raw_dir.rglob("*") if path.is_file()]
    return [path for path in candidates if path.suffix.lower() in {".txt", ".xml", ".html", ".htm"}]


def parse_filing_file(file_path: Path) -> list[dict[str, object]]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    metadata = extract_filing_metadata(text, file_path)
    xml_blocks = extract_xml_blocks(text)
    rows: list[dict[str, object]] = []

    for block in xml_blocks:
        if "infotable" not in block.lower():
            continue
        rows.extend(parse_information_table_xml(block, metadata))

    if not rows and "infotable" in text.lower():
        rows.extend(parse_information_table_xml(text, metadata))

    if rows:
        logger.info("Parsed {} holdings from {}", len(rows), file_path)
    return rows


def extract_xml_blocks(text: str) -> list[str]:
    blocks = re.findall(r"<XML>(.*?)</XML>", text, flags=re.IGNORECASE | re.DOTALL)
    return blocks or [text]


def extract_filing_metadata(text: str, file_path: Path) -> dict[str, object]:
    cik = _first_regex(text, r"CENTRAL INDEX KEY:\s*(\d+)") or _first_cik_from_path(file_path)
    accession = _first_regex(text, r"ACCESSION NUMBER:\s*([0-9\-]+)")
    filing_date = _first_regex(text, r"FILED AS OF DATE:\s*(\d{8})")
    report_period = _first_regex(text, r"CONFORMED PERIOD OF REPORT:\s*(\d{8})")
    institution = institution_by_cik().get(str(cik).zfill(10)) if cik else None
    return {
        "filing_accession": accession,
        "filing_date": _yyyymmdd_to_iso(filing_date),
        "report_period": _yyyymmdd_to_iso(report_period),
        "institution_cik": institution.cik
        if institution
        else str(cik).zfill(10)
        if cik
        else "unknown",
        "institution_name": institution.name if institution else "unknown",
        "manager_type": institution.manager_type.value if institution else "unknown",
        "signal_weight": institution.signal_weight if institution else 0.0,
        "source_file": str(file_path),
    }


def parse_information_table_xml(
    xml_text: str, metadata: dict[str, object]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        root = ET.fromstring(_strip_xml_header(xml_text).encode("utf-8"))
        for info_table in _iter_elements_by_local_name(root, "infoTable"):
            parsed = parse_info_table_element(info_table)
            row = {**metadata, **parsed}
            validated = _validate_row(row)
            if validated is not None:
                rows.append(validated)
        if rows:
            return rows
    except ET.ParseError:
        pass

    soup = BeautifulSoup(xml_text, "xml")
    for info_table in soup.find_all(re.compile("infoTable", re.IGNORECASE)):
        parsed = parse_info_table_soup(info_table)
        row = {**metadata, **parsed}
        validated = _validate_row(row)
        if validated is not None:
            rows.append(validated)
    return rows


def parse_info_table_element(info_table: ET.Element) -> dict[str, object]:
    values: dict[str, object] = {}
    for element in info_table.iter():
        local = _local_name(element.tag).lower()
        if local in _TAG_MAP and element.text is not None:
            values[_TAG_MAP[local]] = element.text.strip()
    return values


def parse_info_table_soup(info_table: object) -> dict[str, object]:
    values: dict[str, object] = {}
    for tag_name, column in _TAG_MAP.items():
        node = info_table.find(re.compile(f"^{tag_name}$", re.IGNORECASE))
        if node and node.text:
            values[column] = node.text.strip()
    return values


def clean_holdings_frame(data: pd.DataFrame) -> pd.DataFrame:
    cleaned = data.copy()
    for column in _NUMERIC_COLUMNS:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    if "cusip" in cleaned.columns:
        cleaned["cusip"] = cleaned["cusip"].map(safe_normalize_cusip)
        cleaned = cleaned[cleaned["cusip"].notna()].copy()
    keys = ["institution_cik", "report_period", "cusip", "put_call", "source_file"]
    available_keys = [column for column in keys if column in cleaned.columns]
    if available_keys:
        cleaned = cleaned.drop_duplicates(subset=available_keys, keep="last")
    return cleaned.reset_index(drop=True)


def _validate_row(row: dict[str, object]) -> dict[str, object] | None:
    try:
        return HoldingRow.model_validate(row).model_dump()
    except ValidationError as exc:
        logger.debug("Skipping invalid holding row: {}", exc)
        return None


def _iter_elements_by_local_name(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for element in root.iter():
        if _local_name(element.tag) == name:
            yield element


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _strip_xml_header(text: str) -> str:
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", text.strip(), count=1, flags=re.IGNORECASE)


def _first_regex(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _first_cik_from_path(file_path: Path) -> str | None:
    for part in file_path.parts:
        if part.isdigit() and 6 <= len(part) <= 10:
            return part
    return None


def _yyyymmdd_to_iso(value: str | None) -> str | None:
    if not value or len(value) != 8:
        return None
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"

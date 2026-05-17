Below is GitHub-safe project write-up. Tone: factual, portfolio-ready, no hype.

---

# Stock 13F Institutional Screener

A local Python dashboard for exploring institutional holdings from SEC 13F filings.

This project was inspired by Huzaifa Zahoor’s Meyka Finance Wire article, *“How I Made a Stock Screener That Shows What Vanguard and BlackRock Own.”* The article describes a workflow for collecting institutional 13F holdings, mapping CUSIPs to stock symbols, deduplicating records, and exposing the results through a screener-style dashboard. 

This implementation rebuilds that idea as a local, SEC-first Python project using open tooling where possible.

## What this project does

The screener downloads and parses SEC 13F-HR filings, extracts institutional holdings, resolves CUSIPs to ticker metadata with OpenFIGI, stores normalized tables in Parquet/ParquetDB, and serves the results through a Streamlit dashboard.

The goal is not to generate buy/sell signals. It is a research tool for asking better questions about institutional ownership, position changes, and manager overlap.

## Current pipeline

```text
SEC 13F-HR filings
  -> raw filing files
  -> parsed holdings
  -> CUSIP normalization
  -> OpenFIGI ticker/FIGI resolution
  -> ParquetDB / Parquet storage
  -> gold analytics tables
  -> Streamlit dashboard
```

## Main features

* SEC 13F-HR download workflow using `sec-edgar-downloader`
* 13F information-table parser for XML and text-like filings
* CUSIP normalization and validation
* Cache-first OpenFIGI resolver with batching, retry logic, backoff, and jitter
* Institution registry with manager categories:

  * passive giants
  * active / signal-rich managers
  * bank / broker complexes
* Local ParquetDB-backed storage with safe Parquet fallback
* Streamlit dashboard with capped table rendering to avoid browser payload overload
* Gold tables for:

  * latest holdings
  * ticker sponsorship
  * position deltas
  * research leads
  * CUSIP mapping diagnostics
* Conda-friendly installation and usage path
* Unit tests for parsing, CUSIP handling, analytics, and storage behavior
* Basic code-health auditing with `pytest`, `radon`, and `ruff`

## Dashboard pages

The Streamlit app currently includes:

* **Dashboard** — data health, CUSIP match rate, top institutional research leads
* **Research Leads** — ranked ticker-level sponsorship table with deterministic tie-breakers
* **Holdings** — latest institutional holdings with filters
* **Ticker Sponsorship** — institution overlap and manager-type counts
* **Position Deltas** — new, increased, decreased, and sold-out positions
* **Mapping Diagnostics** — unresolved CUSIPs and ticker-mapping quality checks

## Design choices

This project intentionally separates raw data from interpreted views.

Passive managers such as BlackRock, Vanguard, and State Street are treated mainly as broad institutional sponsorship indicators. Active or signal-rich managers such as Berkshire Hathaway, Citadel Advisors, and FMR/Fidelity are weighted differently because their filings may be more useful for research triage. Bank and broker complexes are included, but treated as noisier because their 13F filings may aggregate many desks, accounts, and strategies.

The dashboard uses scores only as sorting aids. The output should be interpreted as a research priority list, not as investment advice.

## Current results from test run

A real pipeline run successfully processed:

```text
65 downloaded 13F-HR filings
393,544 parsed holding rows
15,929 unique CUSIPs
352,287 matched holding rows
89.52% row-level CUSIP/ticker match rate
```

The resulting dashboard loads locally in Streamlit and supports filtered browsing/export of institutional ownership data.

## Important limitations

13F filings are delayed and incomplete. They are useful for trend research, but they do not show real-time positioning. They also may omit short positions and may include options, share classes, ADRs, ETFs, or special instruments that require careful interpretation.

CUSIP data has licensing constraints. This project stores CUSIPs as received from SEC filings and stores OpenFIGI-derived mapping metadata separately. It does not redistribute a proprietary CUSIP master dataset.

Ticker mappings can be ambiguous or stale. The project exposes unresolved and special ticker cases rather than silently hiding them.

## Credit

Original idea and product inspiration:

Huzaifa Zahoor, Meyka Finance Wire, *“How I Made a Stock Screener That Shows What Vanguard and BlackRock Own,”* published February 28, 2026.

This project is an independent local Python implementation inspired by that article’s workflow.

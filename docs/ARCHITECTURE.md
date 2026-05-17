# Architecture

## Layers

1. Raw SEC filings on disk.
2. Silver holdings parsed from 13F information tables.
3. Silver CUSIP map cache resolved via OpenFIGI.
4. Resolved holdings.
5. Gold analytical tables.
6. Streamlit dashboard.

## Manager interpretation

Passive giants detect institutional sponsorship. Active/signal-rich managers provide stronger signal candidates. Bank/broker complexes are retained for coverage but down-weighted due to desk/account aggregation noise.

## Request policy

- SEC: default <= 5 requests/second, hard validation <= 10 requests/second.
- OpenFIGI: cache first, batch requests, sleep plus jitter, retry 429/5xx with exponential backoff.

## Storage policy

ParquetDB is preferred. Single-file Parquet fallback remains enabled to keep tests and local demos robust when ParquetDB behavior changes.

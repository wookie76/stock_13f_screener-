# Stock 13F Screener

Local, SEC-first institutional holdings screener.

```text
SEC 13F-HR filings -> raw holdings -> CUSIP resolver -> OpenFIGI cache -> ParquetDB/Parquet -> Streamlit screener
```

This project is a self-learning / portfolio-grade implementation inspired by the 13F institutional screener workflow: pull SEC 13F holdings, map CUSIPs to tickers, dedupe, store, rank, and inspect institutional ownership. It avoids paid market-data APIs by default and keeps FMP-style functionality as an optional future adapter.

## Features

- SEC 13F-HR download wrapper via `sec-edgar-downloader`
- 13F information-table parser for XML and text-like filings
- CUSIP normalization + checksum validation
- Cache-first OpenFIGI CUSIP -> ticker resolver
- Respectful request policy: batching, sleeps, exponential backoff, jitter
- Institution registry with `manager_type` tags:
  - passive giants
  - active/signal-rich managers
  - bank/broker complexes
- ParquetDB-backed table adapter with safe Parquet fallback
- Gold tables:
  - latest holdings
  - ticker sponsorship summary
  - position deltas
- Streamlit dashboard with capped DataFrame display to avoid browser payload errors
- Typer CLI
- Unit tests for parsing, CUSIP validation, scoring, storage fallback

## Recommended environment: Conda

Use Python 3.12 for the cleanest compatibility path. Python 3.14 may work in your current environment, but some data/finance packages can lag new Python releases.

### Bash / zsh

```bash
cd ~/Documents/figi_cusip/stock_13f_screener

conda create -n stock13f python=3.12 -y
conda activate stock13f

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

### Fish shell

```fish
cd ~/Documents/figi_cusip/stock_13f_screener

conda create -n stock13f python=3.12 -y
conda activate stock13f

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

If you keep using an existing environment, such as `yf_314`, install the project into that active environment:

```fish
conda activate yf_314
cd ~/Documents/figi_cusip/stock_13f_screener
python -m pip install -e ".[dev]"
```

## Environment variables

Set SEC identity values and an optional OpenFIGI key.

### Bash / zsh

```bash
export STOCK13F_SEC_COMPANY_NAME="YourNameOrCompany"
export STOCK13F_SEC_EMAIL="first.last@example.com"
export OPENFIGI_API_KEY="your_openfigi_key"
```

### Fish shell

```fish
set -gx STOCK13F_SEC_COMPANY_NAME "YourNameOrCompany"
set -gx STOCK13F_SEC_EMAIL "first.last@example.com"
set -gx OPENFIGI_API_KEY "your_openfigi_key"
```

For persistent fish variables:

```fish
set -Ux STOCK13F_SEC_COMPANY_NAME "YourNameOrCompany"
set -Ux STOCK13F_SEC_EMAIL "first.last@example.com"
set -Ux OPENFIGI_API_KEY "your_openfigi_key"
```

Rotate any API key that was pasted into terminal logs or shared text.

## Verify install

```bash
python -m pytest -q
python -m stock_13f_screener.cli --help
stock13f --help
```

Expected test result:

```text
...... [100%]
```

## Quick smoke test: no network

```bash
stock13f make-example-data --output-dir data
stock13f build-gold   --holdings-path data/silver/holdings_resolved.parquet   --output-dir data/gold
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## Real SEC workflow

Run from project root.

```bash
stock13f download --limit 5
stock13f parse
stock13f resolve-cusips   --holdings-path data/silver/holdings.parquet   --cache-dir data/silver   --output-path data/silver/holdings_resolved.parquet
stock13f build-gold   --holdings-path data/silver/holdings_resolved.parquet   --output-dir data/gold
streamlit run app.py
```

Notes:

- First OpenFIGI run may take several minutes because it resolves unique CUSIPs.
- Later runs reuse the CUSIP cache.
- Use `--cache-dir data/silver`, not a path ending in `.parquet`.
- Dashboard display is capped by default; use filters before increasing row display.

## Common commands

```bash
stock13f list-institutions
stock13f download --limit 1
stock13f parse
stock13f resolve-cusips --help
stock13f build-gold --help
stock13f show-table ticker_sponsorship --layer-dir data/gold --limit 10
```

## Dashboard use

Best workflow:

```text
Research Leads -> Holdings -> Position Deltas -> Mapping Diagnostics
```

Pages:

| Page | Use |
|---|---|
| Dashboard | Data health, CUSIP match rate, score saturation warning |
| Research Leads | Main triage page for ranked tickers |
| Holdings | Drill into who owns a ticker |
| Ticker Sponsorship | Compare broad institutional ownership |
| Position Deltas | Find new, increased, reduced, sold positions |
| Mapping Diagnostics | Inspect unresolved CUSIPs and mapping quality |

Recommended first filters:

```text
Minimum active/signal-rich holders: 1
Minimum passive giant holders: 2 or 3
Exclude special tickers for first pass
Raise minimum value until table is manageable
```

Interpretation:

```text
High passive count = broad sponsorship
High active count = stronger research lead
High bank/broker count = coverage, but noisy
High score = research priority, not buy/sell advice
```

## Development checks

```bash
python -m pytest -q
ruff check .
ruff format .
radon cc -s src
```

Current expected complexity target:

```text
No C/D/F functions.
B-rank parser/API/UI functions are acceptable when domain logic is clear.
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'stock_13f_screener'`

Project is not installed into the active conda environment.

```bash
conda activate stock13f
cd ~/Documents/figi_cusip/stock_13f_screener
python -m pip install -e ".[dev]"
```

Verify:

```bash
python -c "import stock_13f_screener; print(stock_13f_screener.__file__)"
```

### `pytest: command not found`

Use module form:

```bash
python -m pytest -q
```

### Streamlit `MessageSizeError`

Dashboard tried to send too much data to the browser. Use filters and row caps. Do not raise `server.maxMessageSize` unless doing temporary local debugging.

### Streamlit telemetry prompt

Optional opt-out:

```bash
mkdir -p ~/.streamlit
printf "[browser]\ngatherUsageStats = false\n" > ~/.streamlit/config.toml
```

## Important limitations

13F data is delayed and incomplete. It is a research filter, not a buy/sell signal.

CUSIP data has licensing constraints. This project stores CUSIPs received from SEC filings and stores OpenFIGI-derived mapping metadata separately. It does not redistribute a proprietary CUSIP master dataset.

OpenFIGI mappings can be ambiguous. Keep raw CUSIP, ticker, FIGI, security type, exchange, source, and resolved timestamp for auditability.

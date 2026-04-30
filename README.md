# NIFTY50 GitHub Actions Data Pipeline

This repository collects NIFTY50 1-minute OHLC data using the free Yahoo Finance source exposed through `yfinance`, enriches it with technical indicators, and stores idempotent rows in `nifty50sql.db`.

Yahoo Finance uses `^NSEI` for NIFTY 50. The workflow runs every 5 minutes from 09:20-15:40 IST on Monday-Friday, while `main.py` also guards the valid ingestion window. The first useful run is 09:20 IST, which processes the 09:15-09:20 closed candle window.

## Project Structure

```text
main.py                         Pipeline orchestration and market-hours guard
data_fetch.py                   yfinance OHLCV fetch and session filtering
indicators.py                   SMA, EMA, RSI, MACD, Bollinger Bands, VWAP, ATR
db.py                           SQLite schema and duplicate-safe inserts
requirements.txt                Python dependencies
.github/workflows/pipeline.yml  GitHub Actions schedule and database commit
nifty50sql.db                   Generated SQLite database
```

## Deploy on GitHub

1. Push these files to a GitHub repository.
2. Go to `Settings -> Actions -> General -> Workflow permissions`.
3. Enable `Read and write permissions` for `GITHUB_TOKEN`.
4. Commit the workflow file on the default branch.
5. Optionally run `NIFTY50 Data Pipeline` manually from the Actions tab.

No paid API key is required. GitHub cron is UTC, so the workflow maps 09:20-15:40 IST to `03:50-10:10 UTC`; the Python guard is the source of truth for valid market windows.

## Test Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run a safe local smoke test:

```bash
python local_test.py
```

This test fetches recent `^NSEI` 1-minute data, picks the latest available NSE session, computes indicators, writes rows to `nifty50_local_test.db`, prints the latest prepared rows, and reports missing 1-minute intervals. It does not modify the production `nifty50sql.db`.

Inspect the local test database:

```bash
python -c "import sqlite3; con=sqlite3.connect('nifty50_local_test.db'); print(con.execute('SELECT COUNT(*) FROM nifty50').fetchone()); print(con.execute('SELECT * FROM nifty50 ORDER BY timestamp DESC LIMIT 5').fetchall())"
```

To append into the same local test database instead of recreating it:

```bash
python local_test.py --keep-existing
```

If the test returns no rows and Yahoo responds with HTTP `429`, the machine/IP is temporarily rate-limited by Yahoo Finance. Wait a while, try another network, or run again from GitHub Actions.

To test the real scheduled behavior:

```bash
python main.py
```

Outside 09:20-15:30 IST on weekdays, `main.py` should log a skip. During market hours, it writes new rows to `nifty50sql.db`.

## SQLite Schema

The table is named `nifty50`, and `timestamp` is the primary key in `YYYYMMDDHHMM` format. Duplicate runs are safe because existing timestamps are skipped before insert.

```sql
CREATE TABLE nifty50 (
    timestamp TEXT PRIMARY KEY,
    datetime_ist TEXT NOT NULL,
    ticker TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    sma_5 REAL,
    sma_20 REAL,
    ema_5 REAL,
    ema_20 REAL,
    rsi_14 REAL,
    macd REAL,
    macd_signal REAL,
    macd_diff REAL,
    bb_high REAL,
    bb_mid REAL,
    bb_low REAL,
    bb_width REAL,
    atr_14 REAL,
    vwap_14 REAL,
    created_at_utc TEXT NOT NULL
);
```

## Example Row Shape

```text
timestamp     datetime_ist              ticker  open      high      low       close     volume  sma_5     rsi_14  macd
202604300920  2026-04-30 09:20:00+0530  ^NSEI   24610.25  24618.80  24605.10  24615.45  0       24612.37  58.42   3.18
```

Index volume can be zero or unavailable from Yahoo Finance for some intervals. The pipeline still computes price-based indicators and logs missing intervals if Yahoo does not return a complete 5-minute window.

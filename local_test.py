from __future__ import annotations

import logging
import argparse
from pathlib import Path

import pandas as pd

from data_fetch import NIFTY50_TICKER, fetch_nifty50_ohlc, filter_regular_market_session
from db import TABLE_NAME, get_connection, initialize_database, insert_rows
from indicators import add_technical_indicators
from main import configure_logging, prepare_rows_for_database


DEFAULT_LOCAL_DB = Path("nifty50_local_test.db")


def _print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def run_local_test(db_path: Path, keep_existing: bool = False) -> int:
    logger = logging.getLogger(__name__)

    raw_df = fetch_nifty50_ohlc()
    if raw_df.empty:
        logger.error("No rows returned from yfinance for %s", NIFTY50_TICKER)
        return 1

    latest_session_time = raw_df["datetime"].max()
    session_df = filter_regular_market_session(raw_df, latest_session_time)
    if session_df.empty:
        logger.error("Fetched data exists, but no regular NSE session rows were found")
        return 1

    enriched_df = add_technical_indicators(session_df)
    prepared_df = prepare_rows_for_database(enriched_df)

    if db_path.exists() and not keep_existing:
        db_path.unlink()

    with get_connection(db_path) as connection:
        initialize_database(connection)
        inserted_count = insert_rows(connection, prepared_df)
        db_count = connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]

    _print_section("Fetch Summary")
    print(f"Ticker: {NIFTY50_TICKER}")
    print(f"Raw rows fetched: {len(raw_df)}")
    print(f"Latest session rows: {len(session_df)}")
    print(f"Session date: {latest_session_time.date()}")
    print(f"First candle: {session_df['datetime'].min()}")
    print(f"Last candle: {session_df['datetime'].max()}")

    _print_section("Temporary SQLite Test")
    print(f"Database: {db_path.resolve()}")
    print(f"Rows inserted: {inserted_count}")
    print(f"Rows in table: {db_count}")

    _print_section("Latest 5 Prepared Rows")
    display_columns = [
        "timestamp",
        "datetime_ist",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "sma_5",
        "ema_5",
        "rsi_14",
        "macd",
        "vwap_14",
        "atr_14",
    ]
    print(prepared_df[display_columns].tail(5).to_string(index=False))

    expected_one_minute_index = pd.date_range(
        session_df["datetime"].min(),
        session_df["datetime"].max(),
        freq="min",
        tz=session_df["datetime"].dt.tz,
    )
    missing = sorted(set(expected_one_minute_index) - set(session_df["datetime"]))

    _print_section("Interval Check")
    if missing:
        print(f"Missing 1-minute intervals: {len(missing)}")
        print([value.strftime("%Y%m%d%H%M") for value in missing[:20]])
    else:
        print("No missing 1-minute intervals in the fetched session.")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch NIFTY50 data and write it to a visible local test database.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_LOCAL_DB,
        help="SQLite database path to create for local testing. Defaults to nifty50_local_test.db.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing rows in the local test database instead of recreating it.",
    )
    args = parser.parse_args()

    configure_logging()
    raise SystemExit(run_local_test(args.db, args.keep_existing))

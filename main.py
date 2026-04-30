from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from data_fetch import NIFTY50_TICKER, fetch_nifty50_ohlc, filter_regular_market_session
from db import get_connection, initialize_database, insert_rows
from indicators import add_technical_indicators


MARKET_TZ = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
FIRST_PROCESSING_TIME = time(9, 20)
LAST_PROCESSING_TIME = time(15, 40)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def now_ist() -> datetime:
    return datetime.now(MARKET_TZ)


def is_weekday(value: datetime) -> bool:
    return value.weekday() < 5


def latest_closed_five_minute_window(value: datetime) -> tuple[datetime, datetime] | None:
    """Return the most recent closed [start, end) 5-minute market window."""
    value = value.astimezone(MARKET_TZ).replace(second=0, microsecond=0)

    if not is_weekday(value):
        return None

    market_open = value.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute)
    market_close = value.replace(hour=MARKET_CLOSE.hour, minute=MARKET_CLOSE.minute)
    first_processing = value.replace(hour=FIRST_PROCESSING_TIME.hour, minute=FIRST_PROCESSING_TIME.minute)
    last_processing = value.replace(hour=LAST_PROCESSING_TIME.hour, minute=LAST_PROCESSING_TIME.minute)

    if value < first_processing or value > last_processing:
        return None

    elapsed_minutes = int((value - market_open).total_seconds() // 60)
    closed_elapsed_minutes = (elapsed_minutes // 5) * 5
    window_end = market_open + timedelta(minutes=closed_elapsed_minutes)

    if window_end <= market_open:
        return None
    if window_end > market_close:
        window_end = market_close

    return window_end - timedelta(minutes=5), window_end


def prepare_rows_for_database(df: pd.DataFrame, ticker: str = NIFTY50_TICKER) -> pd.DataFrame:
    prepared = df.copy()
    prepared["timestamp"] = prepared["datetime"].dt.strftime("%Y%m%d%H%M")
    prepared["datetime_ist"] = prepared["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    prepared["ticker"] = ticker
    prepared["created_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    numeric_columns = prepared.select_dtypes(include=["float", "int"]).columns
    prepared[numeric_columns] = prepared[numeric_columns].round(6)
    return prepared


def run_pipeline() -> int:
    logger = logging.getLogger(__name__)
    with get_connection() as connection:
        initialize_database(connection)

    current_time = now_ist()
    window = latest_closed_five_minute_window(current_time)

    if window is None:
        logger.info("Skipping run at %s; outside NSE market ingestion window", current_time.isoformat())
        return 0

    window_start, window_end = window
    logger.info("Processing closed window [%s, %s)", window_start.isoformat(), window_end.isoformat())

    raw_df = fetch_nifty50_ohlc()
    if raw_df.empty:
        logger.warning("No source rows available; exiting without database changes")
        return 0

    session_df = filter_regular_market_session(raw_df, current_time)
    if session_df.empty:
        logger.warning("No rows found for today's regular market session")
        return 0

    enriched_df = add_technical_indicators(session_df)
    window_df = enriched_df.loc[
        (enriched_df["datetime"] >= window_start) & (enriched_df["datetime"] < window_end)
    ].copy()

    if window_df.empty:
        logger.warning("No complete 1-minute rows found for target window")
        return 0

    expected_timestamps = pd.date_range(window_start, periods=5, freq="min", tz=MARKET_TZ)
    missing_timestamps = sorted(set(expected_timestamps) - set(window_df["datetime"]))
    if missing_timestamps:
        logger.warning(
            "Missing %d expected intervals from yfinance: %s",
            len(missing_timestamps),
            [ts.strftime("%Y%m%d%H%M") for ts in missing_timestamps],
        )

    prepared_df = prepare_rows_for_database(window_df)
    with get_connection() as connection:
        inserted_count = insert_rows(connection, prepared_df)

    return inserted_count


if __name__ == "__main__":
    configure_logging()
    rows_inserted = run_pipeline()
    logging.getLogger(__name__).info("Pipeline finished; rows_inserted=%d", rows_inserted)

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


LOGGER = logging.getLogger(__name__)
NIFTY50_TICKER = "^NSEI"
MARKET_TZ = ZoneInfo("Asia/Kolkata")


def fetch_nifty50_ohlc(
    ticker: str = NIFTY50_TICKER,
    period: str = "2d",
    interval: str = "1m",
) -> pd.DataFrame:
    """Fetch recent NIFTY50 1-minute OHLCV candles from Yahoo Finance."""
    periods_to_try = [period, "5d", "7d", "1d"]
    seen_periods: set[str] = set()
    raw = pd.DataFrame()

    for candidate_period in periods_to_try:
        if candidate_period in seen_periods:
            continue

        seen_periods.add(candidate_period)
        LOGGER.info(
            "Fetching %s data from yfinance with period=%s interval=%s",
            ticker,
            candidate_period,
            interval,
        )

        try:
            raw = yf.download(
                tickers=ticker,
                period=candidate_period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception:
            LOGGER.exception("yfinance request failed for period=%s", candidate_period)
            raw = pd.DataFrame()

        if not raw.empty:
            break

        LOGGER.warning("No yfinance rows returned for period=%s", candidate_period)

    if raw.empty:
        LOGGER.warning("yfinance returned an empty dataframe for %s", ticker)
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw.reset_index()
    datetime_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(
        columns={
            datetime_col: "datetime",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )

    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce").dt.tz_convert(MARKET_TZ)
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"])

    columns = ["datetime", "open", "high", "low", "close", "volume"]
    if "adj_close" in df.columns:
        columns.append("adj_close")

    for column in ["open", "high", "low", "close", "volume", "adj_close"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df[columns].sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")
    LOGGER.info("Fetched %d cleaned 1-minute rows", len(df))
    return df.reset_index(drop=True)


def filter_regular_market_session(
    df: pd.DataFrame,
    session_date: datetime,
    market_open_hour: int = 9,
    market_open_minute: int = 15,
    market_close_hour: int = 15,
    market_close_minute: int = 30,
) -> pd.DataFrame:
    """Keep rows for a single NSE regular trading session."""
    if df.empty:
        return df

    session_start = session_date.replace(
        hour=market_open_hour,
        minute=market_open_minute,
        second=0,
        microsecond=0,
    )
    session_end = session_date.replace(
        hour=market_close_hour,
        minute=market_close_minute,
        second=0,
        microsecond=0,
    )

    mask = (df["datetime"] >= session_start) & (df["datetime"] < session_end)
    return df.loc[mask].copy().reset_index(drop=True)

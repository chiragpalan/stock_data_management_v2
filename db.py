from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd


LOGGER = logging.getLogger(__name__)
DB_PATH = Path("nifty50sql.db")
TABLE_NAME = "nifty50"

SCHEMA_COLUMNS = [
    "timestamp",
    "datetime_ist",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "sma_5",
    "sma_20",
    "ema_5",
    "ema_20",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_diff",
    "bb_high",
    "bb_mid",
    "bb_low",
    "bb_width",
    "atr_14",
    "vwap_14",
    "created_at_utc",
]


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=DELETE;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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
        """
    )
    connection.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_NAME}_timestamp ON {TABLE_NAME}(timestamp);")
    connection.commit()


def existing_timestamps(connection: sqlite3.Connection, timestamps: Iterable[str]) -> set[str]:
    timestamp_list = list(timestamps)
    if not timestamp_list:
        return set()

    placeholders = ",".join("?" for _ in timestamp_list)
    cursor = connection.execute(
        f"SELECT timestamp FROM {TABLE_NAME} WHERE timestamp IN ({placeholders})",
        timestamp_list,
    )
    return {row[0] for row in cursor.fetchall()}


def insert_rows(connection: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df.empty:
        LOGGER.info("No rows supplied for insert")
        return 0

    insert_df = df[SCHEMA_COLUMNS].copy()
    current_timestamps = existing_timestamps(connection, insert_df["timestamp"].tolist())
    if current_timestamps:
        insert_df = insert_df.loc[~insert_df["timestamp"].isin(current_timestamps)].copy()
        LOGGER.info("Skipped %d duplicate rows", len(current_timestamps))

    if insert_df.empty:
        LOGGER.info("All fetched rows were already present")
        return 0

    insert_df.to_sql(TABLE_NAME, connection, if_exists="append", index=False)
    connection.commit()
    LOGGER.info("Inserted %d new rows into %s", len(insert_df), TABLE_NAME)
    return len(insert_df)

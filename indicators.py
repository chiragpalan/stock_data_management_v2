from __future__ import annotations

import logging

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import VolumeWeightedAveragePrice


LOGGER = logging.getLogger(__name__)


def _empty_indicator(index: pd.Index) -> pd.Series:
    return pd.Series(pd.NA, index=index, dtype="Float64")


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add free technical-analysis indicators to per-minute OHLCV rows."""
    if df.empty:
        return df.copy()

    enriched = df.copy().sort_values("datetime").reset_index(drop=True)
    volume = enriched["volume"].fillna(0)

    enriched["sma_5"] = SMAIndicator(close=enriched["close"], window=5, fillna=False).sma_indicator()
    enriched["sma_20"] = SMAIndicator(close=enriched["close"], window=20, fillna=False).sma_indicator()
    enriched["ema_5"] = EMAIndicator(close=enriched["close"], window=5, fillna=False).ema_indicator()
    enriched["ema_20"] = EMAIndicator(close=enriched["close"], window=20, fillna=False).ema_indicator()
    enriched["rsi_14"] = (
        RSIIndicator(close=enriched["close"], window=14, fillna=False).rsi()
        if len(enriched) >= 14
        else _empty_indicator(enriched.index)
    )

    macd = MACD(close=enriched["close"], window_slow=26, window_fast=12, window_sign=9, fillna=False)
    enriched["macd"] = macd.macd()
    enriched["macd_signal"] = macd.macd_signal()
    enriched["macd_diff"] = macd.macd_diff()

    bollinger = BollingerBands(close=enriched["close"], window=20, window_dev=2, fillna=False)
    enriched["bb_high"] = bollinger.bollinger_hband()
    enriched["bb_mid"] = bollinger.bollinger_mavg()
    enriched["bb_low"] = bollinger.bollinger_lband()
    enriched["bb_width"] = bollinger.bollinger_wband()

    if len(enriched) >= 14:
        atr = AverageTrueRange(
            high=enriched["high"],
            low=enriched["low"],
            close=enriched["close"],
            window=14,
            fillna=False,
        )
        enriched["atr_14"] = atr.average_true_range()
    else:
        enriched["atr_14"] = _empty_indicator(enriched.index)

    if len(enriched) >= 14:
        vwap = VolumeWeightedAveragePrice(
            high=enriched["high"],
            low=enriched["low"],
            close=enriched["close"],
            volume=volume,
            window=14,
            fillna=False,
        )
        enriched["vwap_14"] = vwap.volume_weighted_average_price()
    else:
        enriched["vwap_14"] = _empty_indicator(enriched.index)

    indicator_cols = [
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
    ]
    LOGGER.info("Added %d technical indicator columns", len(indicator_cols))
    return enriched

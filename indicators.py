"""
Расчёт технических индикаторов на основе OHLCV-данных.
Использует библиотеку `ta` поверх pandas DataFrame.
"""
import logging

import numpy as np
import pandas as pd
import ta

import config

logger = logging.getLogger("indicators")


def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Принимает DataFrame со свечами (open, high, low, close, volume)
    и добавляет колонки со всеми индикаторами.
    """
    df = df.copy()

    # --- RSI ---
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=config.RSI_PERIOD).rsi()

    # --- MACD ---
    macd = ta.trend.MACD(
        df["close"],
        window_fast=config.MACD_FAST,
        window_slow=config.MACD_SLOW,
        window_sign=config.MACD_SIGNAL,
    )
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # --- Bollinger Bands ---
    bb = ta.volatility.BollingerBands(df["close"], window=config.BB_PERIOD, window_dev=config.BB_STD)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # --- EMA (9/21/50/200) ---
    for period in config.EMA_PERIODS:
        df[f"ema_{period}"] = ta.trend.EMAIndicator(df["close"], window=period).ema_indicator()

    # --- OBV (On Balance Volume) ---
    df["obv"] = ta.volume.OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()

    # --- Stochastic RSI ---
    stoch_rsi = ta.momentum.StochRSIIndicator(df["close"], window=config.STOCH_RSI_PERIOD)
    df["stoch_rsi_k"] = stoch_rsi.stochrsi_k() * 100
    df["stoch_rsi_d"] = stoch_rsi.stochrsi_d() * 100

    # --- ATR (волатильность) ---
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=config.ATR_PERIOD
    ).average_true_range()
    df["atr_pct"] = df["atr"] / df["close"] * 100

    # --- Volume analysis (средний объём за 20 свечей) ---
    df["volume_sma20"] = df["volume"].rolling(window=20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma20"]

    return df


def find_support_resistance(df: pd.DataFrame, window: int = 20, lookback: int = 100) -> dict:
    """
    Автоматическое определение ближайших уровней поддержки и сопротивления
    на основе локальных минимумов/максимумов за последние `lookback` свечей.
    """
    recent = df.tail(lookback).copy()
    current_price = df["close"].iloc[-1]

    highs = recent["high"].values
    lows = recent["low"].values

    resistance_candidates = []
    support_candidates = []

    for i in range(window, len(recent) - window):
        local_high = highs[i]
        local_low = lows[i]
        if local_high == max(highs[i - window:i + window + 1]):
            resistance_candidates.append(local_high)
        if local_low == min(lows[i - window:i + window + 1]):
            support_candidates.append(local_low)

    resistance_above = [r for r in resistance_candidates if r > current_price]
    support_below = [s for s in support_candidates if s < current_price]

    nearest_resistance = min(resistance_above) if resistance_above else recent["high"].max()
    nearest_support = max(support_below) if support_below else recent["low"].min()

    return {
        "support": round(float(nearest_support), 8),
        "resistance": round(float(nearest_resistance), 8),
        "distance_to_support_pct": round(abs(current_price - nearest_support) / current_price * 100, 3),
        "distance_to_resistance_pct": round(abs(nearest_resistance - current_price) / current_price * 100, 3),
    }


# --- Распознавание свечных паттернов ---
# Реализовано вручную (без TA-Lib, чтобы не тянуть системную зависимость).

def _body(row):
    return abs(row["close"] - row["open"])


def _range(row):
    return row["high"] - row["low"] or 1e-9


def _is_bullish(row):
    return row["close"] > row["open"]


def detect_candlestick_patterns(df: pd.DataFrame) -> list:
    """
    Определяет свечные паттерны на последних свечах.
    Возвращает список найденных паттернов (строки) на последней свече.
    """
    if len(df) < 3:
        return []

    patterns = []
    c0 = df.iloc[-1]  # текущая свеча
    c1 = df.iloc[-2]  # предыдущая
    c2 = df.iloc[-3]  # позапрошлая

    body0 = _body(c0)
    range0 = _range(c0)
    upper_shadow0 = c0["high"] - max(c0["close"], c0["open"])
    lower_shadow0 = min(c0["close"], c0["open"]) - c0["low"]

    # Doji — тело очень маленькое относительно диапазона
    if body0 / range0 < 0.1:
        patterns.append("Doji")

    # Молот / Hammer — маленькое тело сверху, длинная нижняя тень
    if lower_shadow0 > body0 * 2 and upper_shadow0 < body0 and body0 / range0 < 0.35:
        patterns.append("Hammer (молот)")

    # Падающая звезда / Shooting Star
    if upper_shadow0 > body0 * 2 and lower_shadow0 < body0 and body0 / range0 < 0.35:
        patterns.append("Shooting Star (падающая звезда)")

    # Бычье поглощение
    if not _is_bullish(c1) and _is_bullish(c0) and c0["close"] > c1["open"] and c0["open"] < c1["close"]:
        patterns.append("Bullish Engulfing (бычье поглощение)")

    # Медвежье поглощение
    if _is_bullish(c1) and not _is_bullish(c0) and c0["open"] > c1["close"] and c0["close"] < c1["open"]:
        patterns.append("Bearish Engulfing (медвежье поглощение)")

    # Утренняя звезда (3 свечи): медвежья, маленькое тело (гэп вниз), бычья закрывает выше середины первой
    body1 = _body(c1)
    body2 = _body(c2)
    if (not _is_bullish(c2) and body2 > 0 and body1 / (_range(c1)) < 0.3
            and _is_bullish(c0) and c0["close"] > (c2["open"] + c2["close"]) / 2):
        patterns.append("Morning Star (утренняя звезда)")

    # Вечерняя звезда
    if (_is_bullish(c2) and body2 > 0 and body1 / (_range(c1)) < 0.3
            and not _is_bullish(c0) and c0["close"] < (c2["open"] + c2["close"]) / 2):
        patterns.append("Evening Star (вечерняя звезда)")

    # Три белых солдата
    last3 = df.tail(3)
    if all(_is_bullish(r) for _, r in last3.iterrows()) and \
       last3["close"].is_monotonic_increasing:
        patterns.append("Three White Soldiers (три белых солдата)")

    # Три чёрных ворона
    if all(not _is_bullish(r) for _, r in last3.iterrows()) and \
       last3["close"].is_monotonic_decreasing:
        patterns.append("Three Black Crows (три чёрные вороны)")

    # Пинцет сверху/снизу (Tweezer)
    if abs(c0["high"] - c1["high"]) / range0 < 0.02 and not _is_bullish(c0) and _is_bullish(c1):
        patterns.append("Tweezer Top (пинцет сверху)")
    if abs(c0["low"] - c1["low"]) / range0 < 0.02 and _is_bullish(c0) and not _is_bullish(c1):
        patterns.append("Tweezer Bottom (пинцет снизу)")

    return patterns

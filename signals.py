"""
Логика генерации торговых сигналов на основе рассчитанных индикаторов.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

import config
from indicators import calculate_all, find_support_resistance, detect_candlestick_patterns
from ml import load_model, predict as ml_predict

logger = logging.getLogger("signals")

# Загружаем ML-модель при старте
_ml_model = None


def check_higher_tf_alignment(df_higher: pd.DataFrame, direction: str) -> tuple:
    """
    Проверяет тренд на старшем таймфрейме.
    Возвращает (trend_label, is_aligned):
      trend_label: 'бычий' / 'медвежий' / 'боковой'
      is_aligned: True если тренд совпадает с направлением сигнала
    """
    if df_higher is None or len(df_higher) < 200:
        return ("—", False)

    last = df_higher.iloc[-1]

    if pd.isna(last.get("ema_50")) or pd.isna(last.get("ema_200")):
        return ("—", False)

    ema_50 = last["ema_50"]
    ema_200 = last["ema_200"]
    close = last["close"]

    # Определяем тренд на старшем TF
    if close > ema_50 > ema_200:
        trend = "бычий"
    elif close < ema_50 < ema_200:
        trend = "медвежий"
    else:
        trend = "боковой"

    # Проверяем совпадение с направлением сигнала
    aligned = (direction == "UP" and trend == "бычий") or \
              (direction == "DOWN" and trend == "медвежий")

    return (trend, aligned)


@dataclass
class SignalCheck:
    """Результат проверки одного индикатора."""
    name: str
    passed: bool
    detail: str


@dataclass
class Signal:
    symbol: str
    timeframe: str
    direction: str  # "UP" или "DOWN"
    strength_label: str  # Strong / Medium
    strength_pct: int
    confirmations: int
    checks: list = field(default_factory=list)
    price: float = 0.0
    tp_price: float = 0.0
    sl_price: float = 0.0
    atr: float = 0.0
    expiry_minutes: int = 15
    higher_tf_trend: str = "—"  # бычий / медвежий / боковой / —
    higher_tf_aligned: bool = False
    patterns: list = field(default_factory=list)
    support: float = 0.0
    resistance: float = 0.0
    volume_ratio: float = 0.0
    atr_pct: float = 0.0


def _check_up_conditions(last: pd.Series, sr: dict) -> list:
    checks = []

    rsi_ok = last["rsi"] < config.RSI_OVERSOLD
    checks.append(SignalCheck("RSI", rsi_ok, f"{last['rsi']:.1f}"))

    macd_ok = last["macd"] > last["macd_signal"] and last["macd_hist"] > 0
    checks.append(SignalCheck("MACD", macd_ok, "Бычий кросс" if macd_ok else "Нет кросса"))

    bb_ok = last["close"] <= last["bb_lower"] * 1.01
    checks.append(SignalCheck("BB", bb_ok, "У нижней границы" if bb_ok else "В канале"))

    ema_ok = last["close"] > last["ema_50"]
    checks.append(SignalCheck("EMA", ema_ok, "Выше EMA50" if ema_ok else "Ниже EMA50"))

    vol_ok = last["volume_ratio"] >= config.VOLUME_SPIKE_MULTIPLIER
    checks.append(SignalCheck("Volume", vol_ok, f"x{last['volume_ratio']:.1f} от среднего"))

    sr_ok = sr["distance_to_support_pct"] <= 0.5
    checks.append(SignalCheck("S/R", sr_ok, "У поддержки" if sr_ok else "Не у уровня"))

    return checks


def _check_down_conditions(last: pd.Series, sr: dict) -> list:
    checks = []

    rsi_ok = last["rsi"] > config.RSI_OVERBOUGHT
    checks.append(SignalCheck("RSI", rsi_ok, f"{last['rsi']:.1f}"))

    macd_ok = last["macd"] < last["macd_signal"] and last["macd_hist"] < 0
    checks.append(SignalCheck("MACD", macd_ok, "Медвежий кросс" if macd_ok else "Нет кросса"))

    bb_ok = last["close"] >= last["bb_upper"] * 0.99
    checks.append(SignalCheck("BB", bb_ok, "У верхней границы" if bb_ok else "В канале"))

    ema_ok = last["close"] < last["ema_50"]
    checks.append(SignalCheck("EMA", ema_ok, "Ниже EMA50" if ema_ok else "Выше EMA50"))

    vol_ok = last["volume_ratio"] >= config.VOLUME_SPIKE_MULTIPLIER
    checks.append(SignalCheck("Volume", vol_ok, f"x{last['volume_ratio']:.1f} от среднего"))

    sr_ok = sr["distance_to_resistance_pct"] <= 0.5
    checks.append(SignalCheck("S/R", sr_ok, "У сопротивления" if sr_ok else "Не у уровня"))

    return checks


def analyze(df_raw: pd.DataFrame, symbol: str, timeframe: str,
            funding_rate: float = None, orderbook: dict = None,
            df_higher_tf: pd.DataFrame = None) -> Optional[Signal]:
    """
    Главная функция анализа: считает индикаторы, проверяет условия
    и возвращает Signal, если набралось достаточно подтверждений.
    Возвращает None, если сигнала нет (Weak или волатильность слишком низкая).
    """
    if len(df_raw) < 60:
        logger.debug(f"{symbol} {timeframe}: недостаточно данных для анализа")
        return None

    df = calculate_all(df_raw)
    last = df.iloc[-1]

    if pd.isna(last["rsi"]) or pd.isna(last["macd"]) or pd.isna(last["ema_50"]):
        return None

    # Фильтр по волатильности — не даём сигналы в "мёртвом" рынке
    if last["atr_pct"] < config.ATR_MIN_PCT:
        logger.debug(f"{symbol} {timeframe}: волатильность слишком низкая ({last['atr_pct']:.3f}%)")
        return None

    sr = find_support_resistance(df)
    patterns = detect_candlestick_patterns(df)

    up_checks = _check_up_conditions(last, sr)
    down_checks = _check_down_conditions(last, sr)

    # --- Funding Rate Check ---
    funding_check = None
    if funding_rate is not None:
        if funding_rate < config.FUNDING_RATE_BULLISH:
            # Шортит рынок → бычий сигнал
            funding_check = SignalCheck("Funding", True,
                f"{funding_rate*100:.3f}% (бычий)")
        elif funding_rate > config.FUNDING_RATE_BEARISH:
            # Лонгит рынок → медвежий сигнал
            funding_check = SignalCheck("Funding", True,
                f"{funding_rate*100:.3f}% (медвежий)")
        else:
            funding_check = SignalCheck("Funding", False,
                f"{funding_rate*100:.3f}% (нейтральный)")

        up_checks.append(funding_check)
        down_checks.append(funding_check)

    # --- Orderbook Check ---
    if orderbook is not None:
        ratio = orderbook.get("bid_ask_ratio", 1.0)
        spread = orderbook.get("spread_pct", 0)
        imbalance = orderbook.get("imbalance", 0)

        # Бычий: bid/ask > 1.5 (strong bids支撑)
        ob_up_ok = ratio >= config.ORDERBOOK_BID_ASK_RATIO
        ob_up_detail = f"bid/ask={ratio:.2f} (сильные bids)"
        up_checks.append(SignalCheck("Orderbook", ob_up_ok, ob_up_detail))

        # Медвежий: bid/ask < 0.67 (strong asks压力)
        ob_down_ok = ratio <= config.ORDERBOOK_BEARISH_RATIO
        ob_down_detail = f"bid/ask={ratio:.2f} (сильные asks)"
        down_checks.append(SignalCheck("Orderbook", ob_down_ok, ob_down_detail))

        # Штраф за высокий spread (нужен для обоих направлений)
        if spread > config.ORDERBOOK_SPREAD_MAX:
            spread_penalty = SignalCheck("Spread", False, f"{spread:.2f}% (высокий)")
            up_checks.append(spread_penalty)
            down_checks.append(spread_penalty)

    up_score = sum(1 for c in up_checks if c.passed)
    down_score = sum(1 for c in down_checks if c.passed)

    if up_score < config.MIN_CONFIRMATIONS_TO_SEND and down_score < config.MIN_CONFIRMATIONS_TO_SEND:
        return None

    if up_score >= down_score and up_score >= config.MIN_CONFIRMATIONS_TO_SEND:
        direction = "UP"
        checks = up_checks
        score = up_score
    elif down_score >= config.MIN_CONFIRMATIONS_TO_SEND:
        direction = "DOWN"
        checks = down_checks
        score = down_score
    else:
        return None

    total_indicators = len(checks)
    if score >= config.STRONG_THRESHOLD:
        strength_label = "Strong"
    elif score >= config.MEDIUM_THRESHOLD:
        strength_label = "Medium"
    else:
        return None  # Weak — не отправляем

    # --- Multi-Timeframe: проверка тренда на старшем TF ---
    higher_tf_trend = "—"
    higher_tf_aligned = False
    higher_tf = config.TF_HIERARCHY.get(timeframe)
    if higher_tf and df_higher_tf is not None:
        higher_tf_trend, higher_tf_aligned = check_higher_tf_alignment(df_higher_tf, direction)
        # Если старший TF противоречит — снижаем силу сигнала
        if not higher_tf_aligned and higher_tf_trend != "—":
            strength_label = "Medium" if strength_label == "Strong" else None
            if strength_label is None:
                return None  # Слабый сигнал из-за конфликта таймфреймов

    strength_pct = round(score / total_indicators * 100)

    # --- Расчёт TP/SL на основе ATR ---
    atr_val = float(last["atr"])
    entry_price = float(last["close"])

    tf_minutes_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
    tf_minutes = tf_minutes_map.get(timeframe, 5)
    expiry_minutes = tf_minutes * config.SIGNAL_EXPIRY_CANDLES

    if direction == "UP":
        tp_price = entry_price + atr_val * config.TP_ATR_MULTIPLIER
        sl_price = entry_price - atr_val * config.SL_ATR_MULTIPLIER
    else:
        tp_price = entry_price - atr_val * config.TP_ATR_MULTIPLIER
        sl_price = entry_price + atr_val * config.SL_ATR_MULTIPLIER

    return Signal(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        strength_label=strength_label,
        strength_pct=strength_pct,
        confirmations=score,
        checks=checks,
        price=entry_price,
        tp_price=round(tp_price, 8),
        sl_price=round(sl_price, 8),
        atr=round(atr_val, 8),
        expiry_minutes=expiry_minutes,
        higher_tf_trend=higher_tf_trend,
        higher_tf_aligned=higher_tf_aligned,
        patterns=patterns,
        support=sr["support"],
        resistance=sr["resistance"],
        volume_ratio=float(last["volume_ratio"]) if not pd.isna(last["volume_ratio"]) else 0.0,
        atr_pct=float(last["atr_pct"]),
    )


def format_signal_message(signal: Signal) -> str:
    """Форматирует сигнал в текстовое сообщение для Telegram по заданному шаблону."""
    direction_text = "▲ ВВЕРХ (CALL)" if signal.direction == "UP" else "▼ ВНИЗ (PUT)"

    filled = round(signal.strength_pct / 10)
    bar = "█" * filled + "░" * (10 - filled)

    # Risk/Reward ratio
    risk_reward = "—"
    if signal.sl_price and signal.tp_price and signal.price:
        potential_loss = abs(signal.price - signal.sl_price)
        potential_profit = abs(signal.tp_price - signal.price)
        if potential_loss > 0:
            rr = potential_profit / potential_loss
            risk_reward = f"1:{rr:.1f}"

    lines = [
        "━━━━━━━━━━━━━━━━",
        "📊 ПРОГНОЗ",
        "━━━━━━━━━━━━━━━━",
        f"🪙 Пара: {signal.symbol[:-4]}/{signal.symbol[-4:]}",
        f"⏰ Таймфрейм: {signal.timeframe}",
    ]

    # Multi-TF trend info
    if signal.higher_tf_trend != "—":
        aligned_icon = "✅" if signal.higher_tf_aligned else "❌"
        lines.append(f"📈 Тренд старшего TF: {signal.higher_tf_trend} {aligned_icon}")

    lines.extend([
        f"📈 Направление: {direction_text}",
        f"💪 Сила: {bar} {signal.strength_pct}% ({signal.strength_label})",
        "━━━━━━━━━━━━━━━━",
    ])

    icons = {"RSI": "📉", "MACD": "📊", "BB": "📦", "EMA": "📶", "Volume": "🔊", "S/R": "🎯", "Funding": "💹", "Orderbook": "📚", "Spread": "📏"}
    for check in signal.checks:
        icon = icons.get(check.name, "•")
        mark = "✅" if check.passed else "❌"
        lines.append(f"{icon} {check.name}: {check.detail} {mark}")

    if signal.patterns:
        lines.append(f"🕯 Паттерн: {', '.join(signal.patterns)}")

    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"🧱 Поддержка: {signal.support} | Сопротивление: {signal.resistance}")

    lines.append(f"💰 Цена входа: {signal.price}")
    lines.append(f"🎯 Тейкпрофит: {signal.tp_price}")
    lines.append(f"🛑 Стоп-лосс: {signal.sl_price}")
    lines.append(f"📐 Risk/Reward: {risk_reward}")
    lines.append(f"⏱ Время жизни: {signal.expiry_minutes} мин")

    risk = "Низкий" if signal.strength_label == "Strong" else "Средний"
    lines.append(f"⚠️ Риск: {risk}")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("⚠️ Не является финансовой рекомендацией. Торговля криптовалютой сопряжена с высоким риском.")

    return "\n".join(lines)

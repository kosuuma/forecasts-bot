"""
Работа с публичными REST API бирж (Binance, Bybit, OKX).
Получение свечей (klines), тикеров и funding rate.
Реализовано простое кэширование на CACHE_TTL_SECONDS секунд,
чтобы не превышать rate limit бирж.
"""
import asyncio
import logging
import time
from typing import Optional

import aiohttp
import pandas as pd

from config import EXCHANGES, CACHE_TTL_SECONDS

logger = logging.getLogger("exchanges")

# Соответствие таймфреймов для разных бирж
TF_MAP = {
    "binance": {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"},
    "bybit": {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240"},
    "okx": {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"},
}

# Простой in-memory кэш: {(exchange, symbol, tf): (timestamp, DataFrame)}
_klines_cache: dict = {}
_ticker_cache: dict = {}


class ExchangeError(Exception):
    """Ошибка при обращении к API биржи."""


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict, retries: int = 3):
    """Выполняет GET-запрос с повторными попытками при ошибках/rate limit."""
    last_exc = None
    for attempt in range(retries):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 429:
                    # Превышен rate limit — ждём и пробуем снова
                    wait = 2 ** attempt
                    logger.warning(f"Rate limit на {url}, жду {wait}с")
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    text = await resp.text()
                    raise ExchangeError(f"HTTP {resp.status} от {url}: {text[:200]}")
                return await resp.json()
        except asyncio.TimeoutError as e:
            last_exc = e
            logger.warning(f"Таймаут запроса к {url}, попытка {attempt + 1}/{retries}")
            await asyncio.sleep(1)
        except aiohttp.ClientError as e:
            last_exc = e
            logger.warning(f"Ошибка соединения с {url}: {e}, попытка {attempt + 1}/{retries}")
            await asyncio.sleep(1)
    raise ExchangeError(f"Не удалось получить данные с {url} после {retries} попыток: {last_exc}")


async def fetch_klines(
    session: aiohttp.ClientSession,
    symbol: str,
    timeframe: str,
    exchange: str = "binance",
    limit: int = 200,
) -> pd.DataFrame:
    """
    Получает свечи (OHLCV) с указанной биржи и возвращает DataFrame с колонками:
    open_time, open, high, low, close, volume
    """
    cache_key = (exchange, symbol, timeframe)
    now = time.time()
    cached = _klines_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1].copy()

    if exchange not in EXCHANGES:
        raise ExchangeError(f"Неизвестная биржа: {exchange}")

    url = EXCHANGES[exchange]["klines_url"]
    tf = TF_MAP[exchange].get(timeframe)
    if tf is None:
        raise ExchangeError(f"Таймфрейм {timeframe} не поддерживается на {exchange}")

    if exchange == "binance":
        params = {"symbol": symbol, "interval": tf, "limit": limit}
        data = await _get_json(session, url, params)
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"
        ])
        df = df[["open_time", "open", "high", "low", "close", "volume"]]

    elif exchange == "bybit":
        # Bybit требует category (linear/spot); используем spot
        params = {"category": "spot", "symbol": symbol, "interval": tf, "limit": limit}
        data = await _get_json(session, url, params)
        rows = data.get("result", {}).get("list", [])
        rows = list(reversed(rows))  # Bybit отдаёт от новых к старым
        df = pd.DataFrame(rows, columns=[
            "open_time", "open", "high", "low", "close", "volume", "turnover"
        ])
        df = df[["open_time", "open", "high", "low", "close", "volume"]]

    elif exchange == "okx":
        okx_symbol = symbol.replace("USDT", "-USDT") if "-" not in symbol else symbol
        params = {"instId": okx_symbol, "bar": tf, "limit": str(limit)}
        data = await _get_json(session, url, params)
        rows = data.get("data", [])
        rows = list(reversed(rows))
        df = pd.DataFrame(rows, columns=[
            "open_time", "open", "high", "low", "close", "volume", "volCcy", "volCcyQuote", "confirm"
        ])
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
    else:
        raise ExchangeError(f"Биржа {exchange} не реализована")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    df = df.dropna().reset_index(drop=True)

    _klines_cache[cache_key] = (now, df)
    return df.copy()


async def fetch_ticker_24h(
    session: aiohttp.ClientSession, symbol: str, exchange: str = "binance"
) -> Optional[dict]:
    """Получает данные тикера за 24ч (цена, изменение %, объём)."""
    cache_key = (exchange, symbol, "ticker")
    now = time.time()
    cached = _ticker_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    url = EXCHANGES[exchange]["ticker_24h_url"]
    try:
        if exchange == "binance":
            data = await _get_json(session, url, {"symbol": symbol})
            result = {
                "last_price": float(data["lastPrice"]),
                "change_pct": float(data["priceChangePercent"]),
                "volume": float(data["volume"]),
            }
        elif exchange == "bybit":
            data = await _get_json(session, url, {"category": "spot", "symbol": symbol})
            item = data.get("result", {}).get("list", [{}])[0]
            result = {
                "last_price": float(item.get("lastPrice", 0)),
                "change_pct": float(item.get("price24hPcnt", 0)) * 100,
                "volume": float(item.get("volume24h", 0)),
            }
        elif exchange == "okx":
            okx_symbol = symbol.replace("USDT", "-USDT") if "-" not in symbol else symbol
            data = await _get_json(session, url, {"instId": okx_symbol})
            item = data.get("data", [{}])[0]
            last = float(item.get("last", 0))
            open24 = float(item.get("open24h", last)) or last
            result = {
                "last_price": last,
                "change_pct": ((last - open24) / open24 * 100) if open24 else 0,
                "volume": float(item.get("vol24h", 0)),
            }
        else:
            return None
    except (ExchangeError, KeyError, IndexError, ValueError) as e:
        logger.error(f"Ошибка получения тикера {symbol} на {exchange}: {e}")
        return None

    _ticker_cache[cache_key] = (now, result)
    return result


async def fetch_funding_rate(
    session: aiohttp.ClientSession, symbol: str, exchange: str = "binance"
) -> Optional[float]:
    """Получает funding rate (актуально для фьючерсов/перпетуалов)."""
    url = EXCHANGES[exchange]["funding_url"]
    try:
        if exchange == "binance":
            data = await _get_json(session, url, {"symbol": symbol})
            return float(data.get("lastFundingRate", 0))
        elif exchange == "bybit":
            data = await _get_json(session, url, {"category": "linear", "symbol": symbol, "limit": 1})
            rows = data.get("result", {}).get("list", [])
            return float(rows[0]["fundingRate"]) if rows else None
        elif exchange == "okx":
            okx_symbol = symbol.replace("USDT", "-USDT-SWAP") if "-" not in symbol else symbol
            data = await _get_json(session, url, {"instId": okx_symbol})
            rows = data.get("data", [])
            return float(rows[0]["fundingRate"]) if rows else None
    except (ExchangeError, KeyError, IndexError, ValueError) as e:
        logger.warning(f"Не удалось получить funding rate {symbol} на {exchange}: {e}")
        return None
    return None


async def fetch_orderbook_depth(
    session: aiohttp.ClientSession, symbol: str, exchange: str = "binance",
    limit: int = 20
) -> Optional[dict]:
    """
    Получает стакан (orderbook) и считает bid/ask ratio, spread, imbalance.
    Возвращает dict с метриками или None при ошибке.
    """
    url = EXCHANGES[exchange]["depth_url"]
    try:
        if exchange == "binance":
            data = await _get_json(session, url, {"symbol": symbol, "limit": limit})
            bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
            asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
        elif exchange == "bybit":
            data = await _get_json(session, url, {"category": "spot", "symbol": symbol, "limit": limit})
            result = data.get("result", {})
            bids = [(float(b[0]), float(b[1])) for b in result.get("b", [])]
            asks = [(float(a[0]), float(a[1])) for a in result.get("a", [])]
        elif exchange == "okx":
            okx_symbol = symbol.replace("USDT", "-USDT") if "-" not in symbol else symbol
            data = await _get_json(session, url, {"instId": okx_symbol, "sz": str(limit)})
            book = data.get("data", [{}])[0]
            bids = [(float(b[0]), float(b[1])) for b in book.get("bids", [])]
            asks = [(float(a[0]), float(a[1])) for a in book.get("asks", [])]
        else:
            return None

        if not bids or not asks:
            return None

        # Метрики стакана
        total_bid_volume = sum(q for _, q in bids)
        total_ask_volume = sum(q for _, q in asks)
        total_volume = total_bid_volume + total_ask_volume

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid
        spread_pct = (spread / best_ask * 100) if best_ask else 0

        bid_ask_ratio = total_bid_volume / total_ask_volume if total_ask_volume > 0 else 999
        imbalance = ((total_bid_volume - total_ask_volume) / total_volume * 100) if total_volume > 0 else 0

        return {
            "bid_ask_ratio": round(bid_ask_ratio, 3),
            "spread_pct": round(spread_pct, 4),
            "imbalance": round(imbalance, 2),  # положительный = больше bids
            "total_bid_volume": round(total_bid_volume, 4),
            "total_ask_volume": round(total_ask_volume, 4),
            "best_bid": best_bid,
            "best_ask": best_ask,
        }
    except (ExchangeError, KeyError, IndexError, ValueError) as e:
        logger.warning(f"Не удалось получить orderbook {symbol} на {exchange}: {e}")
        return None


# ---------------------------------------------------------------------------
# Fear & Greed Index (alternative.me)
# ---------------------------------------------------------------------------
async def fetch_fear_greed_index(session: aiohttp.ClientSession) -> Optional[dict]:
    """
    Получает индекс страха и жадности крипторынка.
    Возвращает {"value": int, "classification": str, "previous": int}
    """
    url = "https://api.alternative.me/fng/?limit=2&format=json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            items = data.get("data", [])
            if len(items) < 1:
                return None
            current = items[0]
            previous = items[1] if len(items) > 1 else current
            return {
                "value": int(current["value"]),
                "classification": current["value_classification"],
                "previous": int(previous["value"]),
                "change": int(current["value"]) - int(previous["value"]),
            }
    except Exception as e:
        logger.warning(f"Не удалось получить Fear & Greed Index: {e}")
        return None


# ---------------------------------------------------------------------------
# Long/Short Ratio (Binance Futures)
# ---------------------------------------------------------------------------
async def fetch_long_short_ratio(
    session: aiohttp.ClientSession, symbol: str, exchange: str = "binance"
) -> Optional[dict]:
    """
    Получает соотношение лонгов/шортов на фьючерсах.
    Возвращает {"long_pct": float, "short_pct": float, "ratio": float}
    """
    try:
        if exchange == "binance":
            url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            params = {"symbol": symbol, "period": "5m", "limit": 1}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data:
                    return None
                item = data[0]
                long_pct = float(item["longAccount"]) * 100
                short_pct = float(item["shortAccount"]) * 100
                ratio = float(item["longShortRatio"])
                return {
                    "long_pct": round(long_pct, 1),
                    "short_pct": round(short_pct, 1),
                    "ratio": round(ratio, 3),
                }
        return None
    except Exception as e:
        logger.debug(f"Не удалось получить Long/Short ratio для {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# Liquidations (Binance Futures)
# ---------------------------------------------------------------------------
async def fetch_liquidations(
    session: aiohttp.ClientSession, symbol: str, exchange: str = "binance"
) -> Optional[dict]:
    """
    Получает данные о ликвидациях за последние 5 минут.
    Возвращает {"long_liquidations": float, "short_liquidations": float,
                 "total": float, "dominant": str}
    """
    try:
        if exchange == "binance":
            # Force Orders — все принудительные ликвидации
            url = "https://fapi.binance.com/fapi/v1/allForceOrders"
            params = {"symbol": symbol, "limit": 50}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data:
                    return None

                long_liq = 0
                short_liq = 0
                for order in data:
                    qty = float(order.get("origQty", 0))
                    price = float(order.get("price", 0))
                    value = qty * price
                    if order.get("side") == "SELL":
                        long_liq += value  # long ликвидируется →卖
                    else:
                        short_liq += value  # short ликвидируется →买

                total = long_liq + short_liq
                dominant = "long" if long_liq > short_liq else "short"

                return {
                    "long_liquidations": round(long_liq, 2),
                    "short_liquidations": round(short_liq, 2),
                    "total": round(total, 2),
                    "dominant": dominant,
                }
        return None
    except Exception as e:
        logger.debug(f"Не удалось получить ликвидации для {symbol}: {e}")
        return None

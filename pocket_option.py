"""
Лёгкий WebSocket-клиент для Pocket Option.
Получение свечей (OHLCV) через WebSocket без Selenium/Chrome.
"""
import asyncio
import json
import logging
import time
from typing import Optional

import aiohttp
import pandas as pd

logger = logging.getLogger("pocket_option")

# PO WebSocket endpoints
PO_WS_URL = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
PO_WS_URL_LIVE = "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket"

# Кэш свечей
_candles_cache: dict = {}
CACHE_TTL = 30


class PocketOptionClient:
    """Асинхронный WebSocket клиент для Pocket Option."""

    def __init__(self, uid: int, secret: str, is_demo: bool = True):
        self.uid = uid
        self.secret = secret
        self.is_demo = is_demo
        self.ws = None
        self.session = None
        self._connected = False
        self._authenticated = False
        self._pending_candles: dict = {}
        self._sid = None

    async def connect(self):
        """Подключение к PO WebSocket."""
        if self._connected:
            return

        url = PO_WS_URL if self.is_demo else PO_WS_URL_LIVE
        self.session = aiohttp.ClientSession()

        try:
            self.ws = await self.session.ws_connect(url)
            self._connected = True
            logger.info("WebSocket подключён к Pocket Option")

            # Запускаем обработчик сообщений
            asyncio.create_task(self._listen())

            # Ждём авторизации
            for _ in range(50):
                if self._authenticated:
                    return True
                await asyncio.sleep(0.1)

            logger.error("Таймаут авторизации PO")
            return False

        except Exception as e:
            logger.error(f"Ошибка подключения к PO: {e}")
            return False

    async def _listen(self):
        """Обработка входящих WebSocket сообщений."""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WS ошибка: {self.ws.exception()}")
                    break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    break
        except Exception as e:
            logger.error(f"Ошибка в listen: {e}")
        finally:
            self._connected = False
            self._authenticated = False

    async def _handle_message(self, data: str):
        """Обработка одного WS сообщения."""
        # Socket.IO ping/pong
        if data == "2":
            await self.ws.send_str("3")
            return

        # Socket.IO handshake
        if data.startswith("0"):
            try:
                handshake = json.loads(data[1:])
                self._sid = handshake.get("sid")
                logger.info(f"Socket.IO handshake: sid={self._sid}")
                # Отправляем connect
                await self.ws.send_str("40")
            except json.JSONDecodeError:
                pass
            return

        # Socket.IO connect ack
        if data.startswith("40"):
            try:
                ack = json.loads(data[2:])
                self._sid = ack.get("sid", self._sid)
            except json.JSONDecodeError:
                pass
            # Отправляем auth
            await self._send_auth()
            return

        # Socket.IO message
        if data.startswith("42"):
            try:
                payload = json.loads(data[2:])
                if isinstance(payload, list) and len(payload) >= 2:
                    event = payload[0]
                    event_data = payload[1]
                    await self._on_event(event, event_data)
            except json.JSONDecodeError:
                pass
            return

    async def _send_auth(self):
        """Отправка авторизации."""
        auth_msg = {
            "uid": self.uid,
            "secret": self.secret,
            "isDemo": 1 if self.is_demo else 0,
            "platform": 1,
        }
        await self.ws.send_str(f'42["auth",{json.dumps(auth_msg)}]')
        logger.info(f"Auth отправлен: uid={self.uid}, demo={self.is_demo}")

    async def _on_event(self, event: str, data):
        """Обработка событий от PO."""
        if event == "user_init":
            self._authenticated = True
            logger.info(f"PO авторизован: uid={data.get('uid')}")

        elif event == "candles":
            # Ответ на запрос свечей
            symbol = data.get("asset", "")
            candles = data.get("candles", [])
            if symbol and candles:
                self._pending_candles[symbol] = candles

        elif event == "candle":
            # Одна новая свеча
            pass

    async def get_candles(self, symbol: str, timeframe: str = "1m", count: int = 200) -> Optional[pd.DataFrame]:
        """
        Получение свечей с PO.
        symbol: например "EURUSD_otc", "GBPUSD", "BTCUSD"
        timeframe: "1m", "5m", "15m", "30m", "1h"
        """
        cache_key = (symbol, timeframe)
        now = time.time()
        cached = _candles_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1].copy()

        if not self._authenticated:
            logger.error("Не авторизован в PO")
            return None

        # Подписываемся на свечи
        self._pending_candles.pop(symbol, None)

        # PO использует разные форматы таймфреймов
        tf_map = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
        period = tf_map.get(timeframe, 60)

        subscribe_msg = {
            "asset": symbol,
            "period": period,
            "request_id": f"candles_{symbol}_{int(time.time())}",
        }
        await self.ws.send_str(f'42["subscribe",{json.dumps(subscribe_msg)}]')

        # Ждём данные
        for _ in range(50):
            if symbol in self._pending_candles:
                raw = self._pending_candles.pop(symbol)
                df = self._parse_candles(raw)
                if df is not None and len(df) > 0:
                    _candles_cache[cache_key] = (now, df.copy())
                    return df
            await asyncio.sleep(0.1)

        logger.warning(f"Таймаут получения свечей для {symbol}")
        return None

    def _parse_candles(self, raw_candles: list) -> Optional[pd.DataFrame]:
        """Парсинг свечей в DataFrame."""
        try:
            rows = []
            for c in raw_candles:
                rows.append({
                    "open_time": c.get("t", c.get("time", 0)),
                    "open": float(c.get("o", c.get("open", 0))),
                    "high": float(c.get("h", c.get("high", 0))),
                    "low": float(c.get("l", c.get("low", 0))),
                    "close": float(c.get("c", c.get("close", 0))),
                    "volume": float(c.get("v", c.get("volume", 0))),
                })
            df = pd.DataFrame(rows)
            if df.empty:
                return None
            df = df.sort_values("open_time").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"Ошибка парсинга свечей: {e}")
            return None

    async def get_available_assets(self) -> list:
        """Получение списка доступных активов."""
        if not self._authenticated:
            return []

        await self.ws.send_str('42["instruments",{}]')
        await asyncio.sleep(1)

        # Парсим из кэша pending или возвращаем дефолт
        return []

    async def disconnect(self):
        """Отключение."""
        self._connected = False
        self._authenticated = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


# --- Удобные функции ---

async def fetch_po_candles(
    uid: int,
    secret: str,
    symbol: str,
    timeframe: str = "1m",
    count: int = 200,
    is_demo: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Одноразовое получение свечей с PO.
    Создаёт подключение, запрашивает свечи, отключается.
    """
    client = PocketOptionClient(uid, secret, is_demo)
    try:
        connected = await client.connect()
        if not connected:
            return None
        return await client.get_candles(symbol, timeframe, count)
    finally:
        await client.disconnect()


# Глобальный клиент для переиспользования соединения
_global_client: Optional[PocketOptionClient] = None


async def get_po_client(uid: int, secret: str, is_demo: bool = True) -> PocketOptionClient:
    """Получить/создать глобальный клиент PO."""
    global _global_client
    if _global_client is None or not _global_client._connected:
        _global_client = PocketOptionClient(uid, secret, is_demo)
        await _global_client.connect()
    return _global_client


async def fetch_po_candles_persistent(
    uid: int,
    secret: str,
    symbol: str,
    timeframe: str = "1m",
    count: int = 200,
    is_demo: bool = True,
) -> Optional[pd.DataFrame]:
    """Получение свечей через постоянное соединение."""
    client = await get_po_client(uid, secret, is_demo)
    return await client.get_candles(symbol, timeframe, count)

"""
Pocket Option WebSocket client.
Candle data via Socket.IO — no Selenium/Chrome needed.
"""
import asyncio
import json
import logging
import time
from typing import Optional

import aiohttp
import pandas as pd

logger = logging.getLogger("pocket_option")

PO_WS_URL_DEMO = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
PO_WS_URL_LIVE = "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket"

_candles_cache: dict = {}
CACHE_TTL = 30


class PocketOptionClient:
    """Async WebSocket client for Pocket Option."""

    def __init__(self, ssid: str, is_demo: bool = True):
        self.ssid = ssid
        self.is_demo = is_demo
        self.ws = None
        self.session = None
        self._connected = False
        self._authenticated = False
        self._pending_candles: dict = {}
        self._pending_instruments = None
        self._sid = None

    async def connect(self):
        if self._connected:
            return True

        url = PO_WS_URL_DEMO if self.is_demo else PO_WS_URL_LIVE
        headers = {"Origin": "https://po.trade/"}
        self.session = aiohttp.ClientSession(headers=headers)

        try:
            self.ws = await self.session.ws_connect(url)
            self._connected = True
            logger.info("WS connected to Pocket Option")

            asyncio.create_task(self._listen())

            for _ in range(50):
                if self._authenticated:
                    return True
                await asyncio.sleep(0.1)

            logger.error("PO auth timeout")
            return False

        except Exception as e:
            logger.error(f"PO connect error: {e}")
            return False

    async def _listen(self):
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WS error: {self.ws.exception()}")
                    break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    break
        except Exception as e:
            logger.error(f"listen error: {e}")
        finally:
            self._connected = False
            self._authenticated = False

    async def _handle_message(self, data: str):
        # Ping/pong
        if data == "2":
            await self.ws.send_str("3")
            return

        # Engine.IO handshake
        if data.startswith("0") and not data.startswith("40"):
            try:
                handshake = json.loads(data[1:])
                self._sid = handshake.get("sid")
                logger.info(f"EIO handshake: sid={self._sid}")
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
            await self._send_auth()
            return

        # Socket.IO event
        if data.startswith("42"):
            try:
                payload = json.loads(data[2:])
                if isinstance(payload, list) and len(payload) >= 2:
                    await self._on_event(payload[0], payload[1])
            except json.JSONDecodeError:
                pass
            return

    async def _send_auth(self):
        """Send the full SSID auth string from browser."""
        await self.ws.send_str(self.ssid)
        logger.info("Auth sent (SSID)")

    async def _on_event(self, event: str, data):
        if event == "user_init":
            self._authenticated = True
            logger.info(f"PO auth OK: uid={data.get('uid')}")

        elif event == "candles":
            symbol = data.get("asset", "")
            candles = data.get("candles", [])
            if symbol and candles:
                self._pending_candles[symbol] = candles
                logger.debug(f"Got {len(candles)} candles for {symbol}")

        elif event == "instruments":
            self._pending_instruments = data
            logger.info("Got instruments list")

        elif event in ("candle", "candles_update"):
            pass

    async def get_candles(self, symbol: str, timeframe: str = "1m", count: int = 200) -> Optional[pd.DataFrame]:
        cache_key = (symbol, timeframe)
        now = time.time()
        cached = _candles_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1].copy()

        if not self._authenticated:
            logger.error("Not authenticated")
            return None

        self._pending_candles.pop(symbol, None)

        tf_map = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
        period = tf_map.get(timeframe, 60)

        subscribe_msg = {
            "asset": symbol,
            "period": period,
            "request_id": f"candles_{symbol}_{int(time.time())}",
        }
        await self.ws.send_str(f'42["subscribe",{json.dumps(subscribe_msg)}]')
        logger.info(f"Subscribed to {symbol} period={period}")

        for _ in range(80):
            if symbol in self._pending_candles:
                raw = self._pending_candles.pop(symbol)
                df = self._parse_candles(raw)
                if df is not None and len(df) > 0:
                    _candles_cache[cache_key] = (now, df.copy())
                    logger.info(f"OK: {len(df)} candles for {symbol}")
                    return df
            await asyncio.sleep(0.1)

        logger.warning(f"Timeout getting candles for {symbol}")
        return None

    def _parse_candles(self, raw_candles: list) -> Optional[pd.DataFrame]:
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
            logger.error(f"Parse candles error: {e}")
            return None

    async def get_instruments(self) -> Optional[dict]:
        if not self._authenticated:
            return None
        self._pending_instruments = None
        await self.ws.send_str('42["instruments",{}]')
        for _ in range(30):
            if self._pending_instruments is not None:
                return self._pending_instruments
            await asyncio.sleep(0.1)
        return None

    async def disconnect(self):
        self._connected = False
        self._authenticated = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


# Global persistent client
_global_client: Optional[PocketOptionClient] = None


async def get_po_client(ssid: str, is_demo: bool = True) -> PocketOptionClient:
    global _global_client
    if _global_client is None or not _global_client._connected:
        _global_client = PocketOptionClient(ssid, is_demo)
        ok = await _global_client.connect()
        if not ok:
            logger.error("Failed to connect to PO")
    return _global_client


async def fetch_po_candles(
    ssid: str,
    symbol: str,
    timeframe: str = "1m",
    count: int = 200,
    is_demo: bool = True,
) -> Optional[pd.DataFrame]:
    client = await get_po_client(ssid, is_demo)
    if client and client._authenticated:
        return await client.get_candles(symbol, timeframe, count)
    return None


async def disconnect_po():
    global _global_client
    if _global_client:
        await _global_client.disconnect()
        _global_client = None

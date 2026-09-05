import asyncio
import aiohttp

async def check():
    async with aiohttp.ClientSession() as s:
        for exchange, url in [
            ("Binance", "https://api.binance.com/api/v3/ticker/24hr"),
            ("Bybit", "https://api.bybit.com/v5/market/tickers"),
        ]:
            try:
                params = {"symbol": "BTCUSDT"} if "binance" in url.lower() else {"category": "spot", "symbol": "BTCUSDT"}
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    d = await r.json()
                    if "binance" in url.lower():
                        price = d.get("lastPrice", "?")
                        print(f"Binance: OK — BTC {price} USDT")
                    else:
                        print(f"Bybit: OK — response keys: {list(d.keys())}")
            except Exception as e:
                print(f"{exchange}: FAIL — {e}")

asyncio.run(check())

"""Test PO WebSocket connection."""
import asyncio
import sys
sys.path.insert(0, r"D:\AI PROJECTS\forecasts bot")

from pocket_option import PocketOptionClient


async def test():
    uid = 140064076
    secret = "9aca9c3cc8e85691bbded020e0c83e"

    client = PocketOptionClient(uid, secret, is_demo=True)
    print("Connecting to PO...")
    ok = await client.connect()

    if not ok:
        print("Connection failed!")
        return

    print("Connected! Fetching EURUSD_otc 1m candles...")
    df = await client.get_candles("EURUSD_otc", "1m", 200)

    if df is not None:
        print(f"Got {len(df)} candles")
        print(df.tail(5).to_string())
    else:
        print("Failed to get candles")

    await client.disconnect()
    print("Disconnected")


asyncio.run(test())

import asyncio, sys
sys.path.insert(0, r"D:\AI PROJECTS\forecasts bot")
sys.stdout.reconfigure(encoding="utf-8")

from pocket_option import PocketOptionClient

SSID = '42["auth",{"session":"afsti8104rm52ue3s3crvu3no2","isDemo":1,"uid":140064076,"platform":2,"isFastHistory":true,"isOptimized":true}]'

async def test():
    client = PocketOptionClient(SSID, is_demo=True)
    print("Connecting...")
    ok = await client.connect()
    print(f"Connected: {ok}")

    if ok:
        print("Fetching EURUSD_otc 1m candles...")
        df = await client.get_candles("EURUSD_otc", "1m", 200)
        if df is not None:
            print(f"Got {len(df)} candles!")
            print(df.tail(3).to_string())
        else:
            print("No candles received")
        await client.disconnect()

asyncio.run(test())

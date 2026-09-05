import asyncio, aiohttp, json, sys
sys.stdout.reconfigure(encoding="utf-8")

SSID = '42["auth",{"session":"afsti8104rm52ue3s3crvu3no2","isDemo":1,"uid":140064076,"platform":2,"isFastHistory":true,"isOptimized":true}]'

async def try_origin(origin):
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    headers = {"Origin": origin} if origin else {}
    print(f"\nTrying origin: {origin or 'NONE'}")
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.ws_connect(url) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        if msg.data.startswith("0") and not msg.data.startswith("40"):
                            await ws.send_str("40")
                        elif msg.data.startswith("40"):
                            await ws.send_str(SSID)
                            await asyncio.sleep(2)
                            print(f"  Result: check below")
                            return
                        elif msg.data == "2":
                            await ws.send_str("3")
                        elif msg.data == "41":
                            print("  -> DISCONNECTED (41)")
                            return
                        elif "user_init" in msg.data:
                            print(f"  -> AUTH OK: {msg.data[:200]}")
                            return
                        else:
                            print(f"  <- {msg.data[:100]}")
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                        print("  -> WS closed")
                        return
    except Exception as e:
        print(f"  Error: {e}")

async def main():
    for origin in [
        "https://po.trade/",
        "https://pocketoption.com/",
        "https://pocket-link19.co/",
        "https://pocketoption.com",
        "",
    ]:
        await try_origin(origin)

asyncio.run(main())

import asyncio, aiohttp, json, sys
sys.stdout.reconfigure(encoding="utf-8")

SSID = '42["auth",{"session":"afsti8104rm52ue3s3crvu3no2","isDemo":1,"uid":140064076,"platform":2,"isFastHistory":true,"isOptimized":true}]'

async def try_origin(origin):
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    headers = {"Origin": origin} if origin else {}
    print(f"\n=== Origin: {origin or 'NONE'} ===")
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.ws_connect(url) as ws:
                auth_sent = False
                for _ in range(20):
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"  <- {msg.data[:150]}")
                        if msg.data.startswith("0") and not msg.data.startswith("40"):
                            await ws.send_str("40")
                        elif msg.data.startswith("40") and not auth_sent:
                            await ws.send_str(SSID)
                            auth_sent = True
                            print("  >> AUTH SENT")
                        elif msg.data == "2":
                            await ws.send_str("3")
                        elif msg.data == "41":
                            print("  ** DISCONNECTED")
                            return
                        elif "user_init" in msg.data:
                            print("  ** AUTH SUCCESS!")
                            return
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                        print("  ** WS CLOSED")
                        return
    except asyncio.TimeoutError:
        print("  ** TIMEOUT")
    except Exception as e:
        print(f"  Error: {e}")

async def main():
    for origin in ["https://po.trade/", "https://pocketoption.com/", ""]:
        await try_origin(origin)

asyncio.run(main())

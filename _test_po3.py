import asyncio, aiohttp, json, sys
sys.stdout.reconfigure(encoding="utf-8")

SSID = '42["auth",{"session":"afsti8104rm52ue3s3crvu3no2","isDemo":1,"uid":140064076,"platform":2,"isFastHistory":true,"isOptimized":true}]'

async def test():
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    headers = {"Origin": "https://po.trade/"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(url) as ws:
            print("Connected!")
            async for msg in ws:
                print(f"  <<< {msg.type} : {msg.data[:300]}")
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if msg.data.startswith("0") and not msg.data.startswith("40"):
                        print("  Handshake, sending 40...")
                        await ws.send_str("40")
                    elif msg.data.startswith("40"):
                        print("  Connect ack, sending SSID...")
                        await ws.send_str(SSID)
                    elif msg.data == "2":
                        await ws.send_str("3")
                        print("  Pong sent")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    print("  WS closed")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"  WS error: {ws.exception()}")
                    break

asyncio.run(test())

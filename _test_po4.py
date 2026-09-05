import asyncio, json, sys
sys.stdout.reconfigure(encoding="utf-8")
import websockets

SSID = '42["auth",{"session":"afsti8104rm52ue3s3crvu3no2","isDemo":1,"uid":140064076,"platform":2,"isFastHistory":true,"isOptimized":true}]'

async def test():
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    extra_headers = {"Origin": "https://po.trade/"}

    async with websockets.connect(url, additional_headers=extra_headers) as ws:
        print("Connected!")
        async for message in ws:
            msg = message if isinstance(message, str) else message.decode()
            print(f"  <<< {msg[:300]}")
            if msg.startswith("0") and not msg.startswith("40"):
                print("  Handshake, sending 40...")
                await ws.send("40")
            elif msg.startswith("40"):
                print("  Connect ack, sending SSID...")
                await ws.send(SSID)
            elif msg == "2":
                await ws.send("3")
                print("  Pong")
            elif msg == "41":
                print("  DISCONNECTED by server!")
                break

asyncio.run(test())

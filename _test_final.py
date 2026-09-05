import asyncio, aiohttp, json, sys
sys.stdout.reconfigure(encoding="utf-8")

SSID = '42["auth",{"sessionToken":"9aca9c3cc8c5e85691bbded020e0c83e","uid":"140064076","lang":"ru","currentUrl":"cabinet/demo-quick-high-low","isChart":1}]'

async def test():
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    headers = {"Origin": "https://po.trade/"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(url) as ws:
            auth_sent = False
            for _ in range(30):
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    print(f"  <- {msg.data[:200]}")
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
                        return False
                    elif "user_init" in msg.data:
                        print("  ** AUTH SUCCESS!")
                        return True
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    print("  ** WS CLOSED")
                    return False
            return False

result = asyncio.run(test())
print(f"\nFinal: {'SUCCESS' if result else 'FAILED'}")

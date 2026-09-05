import asyncio, aiohttp, json

async def test():
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            print("Connected!")
            async for msg in ws:
                print(f"Type={msg.type} Data={msg.data[:300]}")
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if msg.data.startswith("0"):
                        print("Handshake, sending 40...")
                        await ws.send_str("40")
                    elif msg.data.startswith("40"):
                        print("Connect ack, sending auth...")
                        auth = json.dumps({"uid": 140064076, "secret": "9aca9c3cc8e85691bbded020e0c83e", "isDemo": 1, "platform": 1})
                        await ws.send_str('42["auth",' + auth + "]")
                    elif msg.data == "2":
                        await ws.send_str("3")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    print("WS closed")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"WS error: {ws.exception()}")
                    break

asyncio.run(test())

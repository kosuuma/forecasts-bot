import asyncio, json, sys, time
sys.stdout.reconfigure(encoding="utf-8")

import aiohttp

SSID = None
candles_data = None
candles_event = asyncio.Event()
auth_ok = False
auth_event = asyncio.Event()
stream_data_cache = {}
history_new_cache = {}

async def on_message(ws, data):
    global candles_data, auth_ok

    if data == "2":
        await ws.send_str("3")
        return

    if data.startswith("0") and not data.startswith("40"):
        await ws.send_str("40")
        return

    if data.startswith("40"):
        await ws.send_str(SSID)
        print("Auth sent")
        return

    if data == "41":
        print("DISCONNECTED (41)")
        return

    if data.startswith("42"):
        try:
            payload = json.loads(data[2:])
            event = payload[0]
            evt_data = payload[1] if len(payload) > 1 else None
        except:
            return

        if event == "loadHistoryPeriodFast":
            candles_data = evt_data
            candles_event.set()
            count = len(evt_data.get("data", [])) if isinstance(evt_data, dict) else 0
            print(f"  >>> loadHistoryPeriodFast: {count} candles!")
            return

        if event == "updateStream":
            return

        if event == "updateHistoryNewFast":
            return

        # Print non-noisy events
        if event not in ("updateAssets", "successauth", "successupdateBalance",
                         "successupdatePending", "successupdateOpenedDeals",
                         "successupdateClosedDeals", "chafor", "updateCharts",
                         "successfavorite/load", "successindicator/load",
                         "successprice-alert/load", "successai-strategy-multi/get-state",
                         "successupdateOpenedExpresses"):
            print(f"  Event: {event}")

        if event == "successauth":
            auth_ok = True
            auth_event.set()
            print("  AUTH OK!")
            return

        return

    if data.startswith("451-"):
        # Binary event placeholder - skip
        return

async def main():
    url = "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    headers = {"Origin": "https://po.trade/"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(url) as ws:
            print("Connected to PO LIVE")

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await on_message(ws, msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    break

                if auth_ok:
                    break

            if not auth_ok:
                print("Auth failed")
                return

            # Wait a bit for initial data
            await asyncio.sleep(1)

            # Subscribe
            print("Subscribing EURUSD_otc period=60...")
            sub_msg = json.dumps({"asset": "EURUSD_otc", "period": 60})
            await ws.send_str(f'42["changeSymbol",{sub_msg}]')
            await asyncio.sleep(0.5)
            await ws.send_str(f'42["subfor","EURUSD_otc"]')
            await asyncio.sleep(1)

            # Request historical candles
            server_time = int(time.time())
            end_time = int((server_time // 60) * 60)
            idx = int(time.time() * 100)
            candles_msg = {
                "asset": "EURUSD_otc",
                "index": idx,
                "offset": 200,
                "period": 60,
                "time": end_time,
            }
            await ws.send_str(f'42["getCandles",["loadHistoryPeriod",{json.dumps(candles_msg)}]]')
            print(f"Sent getCandles request (time={end_time})")

            # Continue listening for response
            try:
                await asyncio.wait_for(candles_event.wait(), timeout=15)
                if candles_data and "data" in candles_data:
                    data = candles_data["data"]
                    print(f"\n=== GOT {len(data)} CANDLES ===")
                    for c in data[-5:]:
                        print(c)
                else:
                    print("No candle data in response")
            except asyncio.TimeoutError:
                print("Timeout waiting for candles")

            # Keep listening for stream ticks
            print("\nListening for stream ticks (5s)...")
            try:
                await asyncio.wait_for(ws.receive(), timeout=5)
            except asyncio.TimeoutError:
                pass

asyncio.run(main())

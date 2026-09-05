import asyncio, json, sys, time
sys.stdout.reconfigure(encoding="utf-8")

import aiohttp

SSID = None
candles_data = None
candles_event = asyncio.Event()
auth_ok = False
pending_binary = None

async def main():
    global SSID, candles_data, auth_ok, pending_binary

    print("Paste fresh SSID:")
    SSID = input("> ").strip()

    is_live = '"isDemo":0' in SSID or '"isDemo": 0' in SSID
    url = "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket" if is_live \
        else "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    print(f"Mode: {'LIVE' if is_live else 'DEMO'}, URL: {url}")

    headers = {"Origin": "https://po.trade/"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(url) as ws:
            print("WS connected")

            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                        break
                    continue

                data = msg.data

                if data == "2":
                    await ws.send_str("3")
                    continue

                if data.startswith("0") and not data.startswith("40"):
                    await ws.send_str("40")
                    continue

                if data.startswith("40"):
                    await ws.send_str(SSID)
                    print("Auth sent")
                    continue

                if data == "41":
                    print("DISCONNECTED (41) - bad credentials")
                    break

                if data.startswith("451-"):
                    try:
                        jp = data.split("-", 1)[1]
                        parsed = json.loads(jp)
                        pending_binary = parsed[0]
                    except:
                        pass
                    continue

                if data.startswith("42"):
                    try:
                        payload = json.loads(data[2:])
                        event = payload[0]
                        evt_data = payload[1] if len(payload) > 1 else None
                    except:
                        continue

                    if event == "successauth":
                        auth_ok = True
                        print("  AUTH OK!")
                        break

                    if event not in ("updateStream", "updateHistoryNewFast", "chafor",
                                     "updateCharts", "updateOpenedDeals", "updateClosedDeals",
                                     "updateAssets", "successupdateBalance",
                                     "successupdatePending", "successfavorite/load",
                                     "successindicator/load", "successprice-alert/load",
                                     "successai-strategy-multi/get-state",
                                     "successupdateOpenedExpresses"):
                        print(f"  Event: {event}")

            if not auth_ok:
                print("Auth failed")
                return

            # Listen for binary data (assets, etc)
            print("Waiting for initial data (2s)...")
            await asyncio.sleep(2)

            # Drain any pending messages
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.data
                        if data.startswith("451-"):
                            try:
                                jp = data.split("-", 1)[1]
                                parsed = json.loads(jp)
                                pending_binary = parsed[0]
                            except:
                                pass
                        elif data.startswith("42"):
                            try:
                                payload = json.loads(data[2:])
                                event = payload[0]
                                if event not in ("updateStream", "updateHistoryNewFast", "chafor"):
                                    print(f"  Pre: {event}")
                            except:
                                pass
                except asyncio.TimeoutError:
                    break

            # Subscribe
            print("Subscribing EURUSD_otc...")
            await ws.send_str(f'42["changeSymbol",{json.dumps({"asset":"EURUSD_otc","period":60})}]')
            await asyncio.sleep(0.3)
            await ws.send_str('42["subfor","EURUSD_otc"]')
            await asyncio.sleep(1)

            # Drain again
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.3)
                except asyncio.TimeoutError:
                    break

            # Request candles
            end_time = int((int(time.time()) // 60) * 60)
            idx = int(time.time() * 100)
            req = {"asset": "EURUSD_otc", "index": idx, "offset": 200, "period": 60, "time": end_time}
            await ws.send_str(f'42["getCandles",["loadHistoryPeriod",{json.dumps(req)}]]')
            print(f"getCandles sent (time={end_time})")

            # Listen for response
            for _ in range(300):
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    data = msg.data

                    if data == "2":
                        await ws.send_str("3")
                        continue

                    if data.startswith("451-"):
                        try:
                            jp = data.split("-", 1)[1]
                            parsed = json.loads(jp)
                            pending_binary = parsed[0]
                            if pending_binary == "loadHistoryPeriodFast":
                                print("  loadHistoryPeriodFast text received, waiting binary...")
                        except:
                            pass
                        continue

                    if data.startswith("42"):
                        try:
                            payload = json.loads(data[2:])
                            event = payload[0]
                            if event == "loadHistoryPeriodFast":
                                candles_data = payload[1] if len(payload) > 1 else payload
                                count = len(candles_data.get("data", [])) if isinstance(candles_data, dict) else 0
                                print(f"\n=== GOT {count} CANDLES ===")
                                if count > 0:
                                    for c in candles_data["data"][-5:]:
                                        print(c)
                                return
                            if event not in ("updateStream", "updateHistoryNewFast"):
                                print(f"  Response: {event}")
                        except:
                            pass
                        continue

                    # Binary data (not string)
                    if pending_binary == "loadHistoryPeriodFast":
                        actual = data
                        if isinstance(data, bytes):
                            try:
                                actual = json.loads(data.decode("utf-8"))
                            except:
                                pass
                        if isinstance(actual, dict) and "data" in actual:
                            candles_data = actual
                            print(f"\n=== GOT {len(actual['data'])} CANDLES ===")
                            for c in actual["data"][-5:]:
                                print(c)
                            return
                        pending_binary = None

                except asyncio.TimeoutError:
                    print("Timeout")
                    break

            print("No candles received")

asyncio.run(main())

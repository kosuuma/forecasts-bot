import asyncio, json, sys, time
sys.stdout.reconfigure(encoding="utf-8")

import websockets

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
    print(f"Mode: {'LIVE' if is_live else 'DEMO'}")

    extra_headers = {"Origin": "https://po.trade/"}

    async with websockets.connect(url, additional_headers=extra_headers) as ws:
        print("WS connected")

        async for msg in ws:
            data = msg if isinstance(msg, str) else msg.decode()

            if data == "2":
                await ws.send("3")
                continue

            if data.startswith("0") and not data.startswith("40"):
                await ws.send("40")
                continue

            if data.startswith("40"):
                await ws.send(SSID)
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

        # Drain initial data
        print("Draining initial data...")
        for _ in range(50):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                data = msg if isinstance(msg, str) else msg.decode()
                if data.startswith("451-"):
                    try:
                        jp = data.split("-", 1)[1]
                        parsed = json.loads(jp)
                        pending_binary = parsed[0]
                    except:
                        pass
            except asyncio.TimeoutError:
                break

        # Subscribe
        print("Subscribing EURUSD_otc...")
        await ws.send(f'42["changeSymbol",{json.dumps({"asset":"EURUSD_otc","period":60})}]')
        await asyncio.sleep(0.3)
        await ws.send('42["subfor","EURUSD_otc"]')
        await asyncio.sleep(1)

        # Drain
        for _ in range(50):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.3)
            except asyncio.TimeoutError:
                break

        # Request candles
        end_time = int((int(time.time()) // 60) * 60)
        idx = int(time.time() * 100)
        req = {"asset": "EURUSD_otc", "index": idx, "offset": 200, "period": 60, "time": end_time}
        await ws.send(f'42["getCandles",["loadHistoryPeriod",{json.dumps(req)}]]')
        print(f"getCandles sent (time={end_time})")

        # Listen for response
        for _ in range(500):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = msg if isinstance(msg, str) else msg.decode()

                if data == "2":
                    await ws.send("3")
                    continue

                if data.startswith("451-"):
                    try:
                        jp = data.split("-", 1)[1]
                        parsed = json.loads(jp)
                        pending_binary = parsed[0]
                        if pending_binary == "loadHistoryPeriodFast":
                            print("  loadHistoryPeriodFast placeholder received")
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

                # Binary data
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
                print("Timeout waiting for candles")
                break

        print("No candles received")

asyncio.run(main())

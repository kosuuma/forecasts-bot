import sys, time, os, asyncio, json
sys.stdout.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("Paste fresh SSID:")
ssid = input("> ").strip()

from pocketoptionapi import PocketOption
from pocketoptionapi.ws.client import WebsocketClient
from pocketoptionapi.ws import global_value

def patched_build(self):
    return ssid
WebsocketClient._build_auth_message = patched_build

orig_connect = WebsocketClient.connect
async def patched_connect(self, *a, **kw):
    self.regions = ["DEMO"]
    self.demo_regions = ["DEMO"]
    self.real_regions = ["REAL"]
    return await orig_connect(self, *a, **kw)
WebsocketClient.connect = patched_connect

candles_event = asyncio.Event()
candles_result = None

orig_on_message = WebsocketClient.on_message
async def patched_on_message(self, message):
    global candles_result

    if isinstance(message, bytes):
        try:
            decoded = message.decode("utf-8")
            data = json.loads(decoded)
            if isinstance(data, list) and len(data) > 0:
                msg_type = data[0]
                payload = data[1] if len(data) > 1 else None

                if msg_type == "loadHistoryPeriodFast":
                    candles_result = payload
                    candles_event.set()
                    count = len(payload.get("data", [])) if isinstance(payload, dict) else 0
                    print(f"  >>> loadHistoryPeriodFast: {count} candles!")
                    return

                # For all other binary events, decode properly
                if payload and isinstance(payload, dict) and payload.get("_placeholder"):
                    # Need to read the actual binary data
                    try:
                        binary_data = await asyncio.wait_for(self.websocket.recv(), timeout=5)
                        if isinstance(binary_data, bytes):
                            actual_data = json.loads(binary_data.decode("utf-8"))
                        else:
                            actual_data = binary_data
                    except:
                        actual_data = payload
                else:
                    actual_data = payload

                if msg_type == "successauth":
                    print(f"  AUTH OK! balance={actual_data.get('balance', '?') if isinstance(actual_data, dict) else '?'}")
                    global_value.account_id = actual_data.get("id") or actual_data.get("accountId") if isinstance(actual_data, dict) else None
                    await self._mark_connected_and_post_auth()
                    return
                elif msg_type == "updateAssets":
                    await self._handle_assets_update(actual_data)
                    return
                elif msg_type == "successupdateBalance":
                    if isinstance(actual_data, dict):
                        await self._handle_balance_update(actual_data)
                    return
                elif msg_type == "updateStream":
                    if isinstance(actual_data, list) and actual_data and isinstance(actual_data[0], list):
                        stream_data = actual_data[0]
                        if len(stream_data) >= 3:
                            self.api.time_sync.synchronize(stream_data[1])
                            self.api._on_stream_tick(stream_data[0], stream_data[1], stream_data[2])
                    return
                elif msg_type == "updateHistoryNewFast":
                    if isinstance(actual_data, dict) and "asset" in actual_data:
                        self.api._on_history_new_fast(actual_data)
                    return
                elif msg_type in ("successupdatePending", "successupdateOpenedDeals",
                                   "successupdateClosedDeals", "chafor", "updateCharts"):
                    return
                else:
                    print(f"  BIN: {msg_type}")
            elif isinstance(data, dict):
                pass  # chart settings, deals, etc
        except Exception as e:
            print(f"  BIN err: {e}")
        return

    if message.startswith("451-["):
        try:
            json_part = message.split("-", 1)[1]
            msg_data = json.loads(json_part)
            msg_type = msg_data[0]
            if msg_type not in ("updateStream", "updateHistoryNewFast", "chafor",
                                 "updateCharts", "updateOpenedDeals", "updateClosedDeals",
                                 "updateAssets", "successauth", "successupdateBalance",
                                 "successupdatePending", "successfavorite/load",
                                 "successindicator/load", "successprice-alert/load",
                                 "successai-strategy-multi/get-state",
                                 "successupdateOpenedExpresses"):
                print(f"  451: {msg_type}")
        except:
            pass
        return

    if not message.startswith("0{") and message != "2" and not message.startswith("40{"):
        pass
    await self._handle_text_message(message)
WebsocketClient.on_message = patched_on_message

api = PocketOption(ssid)
ok, err = api.connect()
print(f"Connect: ok={ok}, err={err}")

if ok:
    for i in range(100):
        if api.check_connect() and api.is_time_synced():
            print(f"Connected & synced! ({i*0.1:.1f}s)")
            break
        time.sleep(0.1)
    else:
        print(f"Connected={api.check_connect()}, Synced={api.is_time_synced()}")

    if api.check_connect():
        server_time = api.api.time_sync.get_server_native_time()
        period = 60
        end_time = int((server_time // period) * period)
        print(f"Server time: {server_time}, request time: {end_time}")

        print("Subscribing EURUSD_otc period=60...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(1)

        # Send getCandles directly
        idx = int(time.time() * 100)
        msg = f'42["getCandles",["loadHistoryPeriod",{{"asset":"EURUSD_otc","index":{idx},"offset":200,"period":60,"time":{end_time}}}]]'
        print(f"Sending getCandles...")
        await_coro = api.websocket.send_message(msg)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            task = loop.create_task(await_coro)
            loop.run_until_complete(asyncio.sleep(0.5))
        else:
            loop.run_until_complete(await_coro)

        print("Waiting for candles...")
        try:
            loop2 = asyncio.new_event_loop()
            loop2.run_until_complete(asyncio.wait_for(candles_event.wait(), timeout=15))
            if candles_result and "data" in candles_result:
                data = candles_result["data"]
                print(f"\n=== GOT {len(data)} CANDLES ===")
                for c in data[-5:]:
                    print(c)
            else:
                print("No candle data")
        except asyncio.TimeoutError:
            print("Timeout - no loadHistoryPeriodFast")

    api.disconnect_websocket()

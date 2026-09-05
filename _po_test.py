import sys, time, os, asyncio, json
sys.stdout.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("Paste fresh SSID (with session, isDemo, uid, platform):")
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

                if msg_type == "updateHistoryNewFast":
                    if isinstance(payload, dict) and "asset" in payload:
                        self.api._on_history_new_fast(payload)
                    return

                if msg_type == "updateStream":
                    if isinstance(payload, list) and payload and isinstance(payload[0], list):
                        sd = payload[0]
                        if len(sd) >= 3:
                            self.api.time_sync.synchronize(sd[1])
                            self.api._on_stream_tick(sd[0], sd[1], sd[2])
                    return

                # For 451-placeholder binary events, read actual binary data
                if isinstance(payload, dict) and payload.get("_placeholder"):
                    try:
                        bin_data = await asyncio.wait_for(self.websocket.recv(), timeout=5)
                        actual = json.loads(bin_data.decode("utf-8")) if isinstance(bin_data, bytes) else bin_data
                    except:
                        actual = payload
                else:
                    actual = payload

                if msg_type == "successauth":
                    if isinstance(actual, dict):
                        global_value.account_id = actual.get("id") or actual.get("accountId")
                    await self._mark_connected_and_post_auth()
                    print(f"  AUTH OK!")
                    return
                elif msg_type == "updateAssets":
                    await self._handle_assets_update(actual)
                    return
                elif msg_type == "successupdateBalance":
                    if isinstance(actual, dict):
                        await self._handle_balance_update(actual)
                    return
                elif msg_type in ("successupdatePending", "successupdateOpenedDeals",
                                   "successupdateClosedDeals", "chafor", "updateCharts",
                                   "successfavorite/load", "successindicator/load",
                                   "successprice-alert/load", "successai-strategy-multi/get-state",
                                   "successupdateOpenedExpresses"):
                    return
                else:
                    print(f"  BIN: {msg_type}")

            elif isinstance(data, dict):
                pass  # chart settings, deals
        except Exception as e:
            pass
        return

    if message.startswith("451-["):
        return

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
        print(f"check_connect={api.check_connect()}, is_time_synced={api.is_time_synced()}")

    if api.check_connect():
        server_time = api.api.time_sync.get_server_native_time()
        end_time = int((server_time // 60) * 60)
        print(f"Server time: {server_time}")

        print("Subscribing EURUSD_otc...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(1)

        # Send getCandles directly
        idx = int(time.time() * 100)
        msg = f'42["getCandles",["loadHistoryPeriod",{{"asset":"EURUSD_otc","index":{idx},"offset":200,"period":60,"time":{end_time}}}]]'
        print("Sending getCandles...")
        coro = api.websocket.send_message(msg)
        if asyncio.get_event_loop().is_running():
            asyncio.get_event_loop().create_task(coro)
        else:
            asyncio.get_event_loop().run_until_complete(coro)

        print("Waiting for loadHistoryPeriodFast...")
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(asyncio.wait_for(candles_event.wait(), timeout=15))
            if candles_result and "data" in candles_result:
                data = candles_result["data"]
                print(f"\n=== GOT {len(data)} CANDLES ===")
                for c in data[-5:]:
                    print(c)
            else:
                print("No candle data")
        except asyncio.TimeoutError:
            print("Timeout - no response")

    api.disconnect_websocket()

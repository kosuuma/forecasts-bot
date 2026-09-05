import sys, time, os, asyncio, json, threading
sys.stdout.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("Paste fresh SSID:")
ssid = input("> ").strip()

from pocketoptionapi import PocketOption
from pocketoptionapi.ws.client import WebsocketClient, global_value

def patched_build(self):
    return ssid
WebsocketClient._build_auth_message = patched_build

is_demo = '"isDemo":1' in ssid or '"isDemo": 1' in ssid
print(f"Mode: {'DEMO' if is_demo else 'LIVE'}")

orig_connect = WebsocketClient.connect
async def patched_connect(self, *a, **kw):
    if is_demo:
        self.regions = ["DEMO"]
        self.demo_regions = ["DEMO"]
    else:
        self.regions = ["LIVE", "LIVE_2"]
        self.real_regions = ["LIVE", "LIVE_2"]
        self.demo_regions = []
    return await orig_connect(self, *a, **kw)
WebsocketClient.connect = patched_connect

candles_ready = threading.Event()
candles_result = [None]
pending_binary_type = [None]
ws_loop = [None]

orig_on_message = WebsocketClient.on_message
async def patched_on_message(self, message):
    if ws_loop[0] is None:
        ws_loop[0] = asyncio.get_event_loop()

    if isinstance(message, str):
        if message.startswith("451-["):
            try:
                jp = message.split("-", 1)[1]
                parsed = json.loads(jp)
                pending_binary_type[0] = parsed[0]
            except:
                pass
            return
        await self._handle_text_message(message)
        return

    actual = message
    if isinstance(message, bytes):
        try:
            actual = json.loads(message.decode("utf-8"))
        except:
            return

    msg_type = pending_binary_type[0]
    pending_binary_type[0] = None

    if msg_type is None:
        return

    if msg_type == "successauth":
        if isinstance(actual, dict):
            global_value.account_id = actual.get("id") or actual.get("accountId")
        await self._mark_connected_and_post_auth()
        print("  AUTH OK!")
        return

    if msg_type == "loadHistoryPeriodFast":
        candles_result[0] = actual
        candles_ready.set()
        if isinstance(actual, dict):
            self.api.history_data = actual
            self.api._history_data_event.set()
        count = len(actual.get("data", [])) if isinstance(actual, dict) else 0
        print(f"  >>> loadHistoryPeriodFast: {count} candles!")
        return

    if msg_type == "updateAssets":
        if isinstance(actual, (list, dict)):
            await self._handle_assets_update(actual)
        return

    if msg_type == "successupdateBalance":
        if isinstance(actual, dict):
            await self._handle_balance_update(actual)
        return

    if msg_type == "updateStream":
        if isinstance(actual, list) and actual and isinstance(actual[0], list):
            sd = actual[0]
            if len(sd) >= 3:
                self.api.time_sync.synchronize(sd[1])
                self.api._on_stream_tick(sd[0], sd[1], sd[2])
        return

    if msg_type == "updateHistoryNewFast":
        if isinstance(actual, dict) and "asset" in actual:
            self.api._on_history_new_fast(actual)
        return

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
        print(f"check={api.check_connect()} sync={api.is_time_synced()}")

    if api.check_connect():
        print("Subscribing EURUSD_otc...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(2)

        # Send getCandles via the websocket's event loop
        server_time = api.api.time_sync.get_server_native_time()
        end_time = int((server_time // 60) * 60)
        idx = int(time.time() * 100)
        req = {"asset": "EURUSD_otc", "index": idx, "offset": 200, "period": 60, "time": end_time}
        raw_msg = f'42["getCandles",["loadHistoryPeriod",{json.dumps(req)}]]'

        ws_raw = api.api.websocket.websocket
        print(f"Sending getCandles (time={end_time})...")

        # Use asyncio.run_coroutine_threadsafe to send from main thread to ws thread
        if ws_loop[0]:
            future = asyncio.run_coroutine_threadsafe(ws_raw.send(raw_msg), ws_loop[0])
            future.result(timeout=5)
            print("Sent!")
        else:
            # Fallback: try library's send_message
            api.api.websocket.send_message(raw_msg)
            print("Sent via send_message!")

        print("Waiting for candles...")
        candles_ready.wait(timeout=15)

        if candles_result[0] and isinstance(candles_result[0], dict) and "data" in candles_result[0]:
            data = candles_result[0]["data"]
            print(f"\n=== GOT {len(data)} CANDLES ===")
            for c in data[-5:]:
                print(c)
        else:
            print("No candle data received")

    api.disconnect_websocket()

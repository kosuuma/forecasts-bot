import sys, time, os, asyncio, json
sys.stdout.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("Paste fresh SSID:")
ssid = input("> ").strip()

from pocketoptionapi import PocketOption
from pocketoptionapi.ws.client import WebsocketClient

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
ws_ref = None

orig_on_message = WebsocketClient.on_message
async def patched_on_message(self, message):
    global candles_result, ws_ref
    ws_ref = self.websocket

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
                elif msg_type not in ("updateStream", "updateHistoryNewFast", "chafor"):
                    print(f"  BIN: {msg_type}")
            elif isinstance(data, dict):
                if "chart_id" in data or "settings" in data:
                    pass  # skip chart settings
                elif "openTime" in data:
                    pass  # skip deal data
                else:
                    print(f"  BIN dict: {list(data.keys())[:5]}")
        except Exception as e:
            print(f"  BIN raw: {len(message)} bytes, err={e}")
        return

    if message.startswith("451-["):
        try:
            json_part = message.split("-", 1)[1]
            msg_data = json.loads(json_part)
            msg_type = msg_data[0]
            if msg_type == "loadHistoryPeriodFast":
                print(f"  451: loadHistoryPeriodFast (waiting binary...)")
            elif msg_type not in ("updateStream", "updateHistoryNewFast", "chafor",
                                   "updateCharts", "updateOpenedDeals", "updateClosedDeals",
                                   "updateAssets", "successauth", "successupdateBalance",
                                   "successupdatePending"):
                print(f"  451: {msg_type}")
        except:
            pass
        return

    if not message.startswith("0{") and message != "2" and not message.startswith("40{"):
        print(f"  TEXT: {message[:120]}")
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

    if api.check_connect():
        # Get server time for request
        server_time = api.api.time_sync.get_server_native_time()
        period = 60
        end_time = int((server_time // period) * period)
        print(f"Server time: {server_time}, request time: {end_time}")

        # Subscribe
        print("Subscribing...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(1)

        # Send getCandles DIRECTLY via websocket
        idx = int(time.time() * 100)
        msg = f'42["getCandles",["loadHistoryPeriod",{{"asset":"EURUSD_otc","index":{idx},"offset":200,"period":60,"time":{end_time}}}]]'
        print(f"Sending getCandles directly...")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ws_ref.send(msg))
        print("Sent! Waiting for response...")

        # Wait for response
        try:
            loop.run_until_complete(asyncio.wait_for(candles_event.wait(), timeout=10))
            if candles_result and "data" in candles_result:
                data = candles_result["data"]
                print(f"\n=== GOT {len(data)} CANDLES ===")
                for c in data[-5:]:
                    print(c)
            else:
                print("No data in response")
        except asyncio.TimeoutError:
            print("Timeout - no loadHistoryPeriodFast")
            print("Trying alternative: updateHistoryNewFast...")

    api.disconnect_websocket()

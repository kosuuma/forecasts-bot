import sys, time, os, asyncio, json
sys.stdout.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("Paste fresh SSID:")
ssid = input("> ").strip()

from pocketoptionapi import PocketOption
from pocketoptionapi.ws.client import WebsocketClient

# Patch auth
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

# Patch on_message: intercept ALL 451 binary events directly
candles_received = asyncio.Event()
candles_data = None

orig_on_message = WebsocketClient.on_message
async def patched_on_message(self, message):
    global candles_data
    if isinstance(message, bytes):
        try:
            decoded = message.decode("utf-8")
            data = json.loads(decoded)
            msg_type = data[0] if isinstance(data, list) and data else "unknown"
            if msg_type == "loadHistoryPeriodFast":
                payload = data[1] if len(data) > 1 else data
                candles_data = payload
                candles_received.set()
                print(f"  >>> loadHistoryPeriodFast: {len(payload.get('data', []))} candles")
                return
            elif msg_type == "updateStream":
                pass  # skip noisy stream
            else:
                print(f"  BINARY: {msg_type}")
        except:
            print(f"  BINARY: {len(message)} bytes raw")
        return

    # Text messages
    if message.startswith("451-["):
        try:
            json_part = message.split("-", 1)[1]
            msg_data = json.loads(json_part)
            msg_type = msg_data[0]
            if msg_type == "loadHistoryPeriodFast":
                print(f"  451 text: {msg_type} (waiting for binary data...)")
                return
            elif msg_type not in ("updateStream", "updateHistoryNewFast", "chafor",
                                   "updateCharts", "updateOpenedDeals", "updateClosedDeals"):
                print(f"  451: {msg_type}")
        except:
            print(f"  451 raw: {message[:100]}")
        return

    # Non-451 text
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
        # Subscribe first
        print("Subscribing EURUSD_otc period=60...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(2)

        # Manually send getCandles request
        import time as _time
        now = int(_time.time())
        idx = int(_time.time() * 100)
        getcandles_msg = f'42["getCandles",["loadHistoryPeriod",{{"asset":"EURUSD_otc","index":{idx},"offset":200,"period":60,"time":{now}}}]]'
        print(f"Sending getCandles request...")
        asyncio.get_event_loop().run_until_complete(api.websocket.send_message(getcandles_msg))

        # Wait for response
        print("Waiting for candles...")
        try:
            asyncio.get_event_loop().run_until_complete(
                asyncio.wait_for(candles_received.wait(), timeout=10)
            )
            if candles_data and "data" in candles_data:
                data = candles_data["data"]
                print(f"\n=== GOT {len(data)} CANDLES ===")
                for c in data[-5:]:
                    print(c)
            else:
                print("No candle data")
        except asyncio.TimeoutError:
            print("Timeout - no loadHistoryPeriodFast received")

    api.disconnect_websocket()

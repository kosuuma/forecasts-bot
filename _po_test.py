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

# Patch to single region
orig_connect = WebsocketClient.connect
async def patched_connect(self, *a, **kw):
    self.regions = ["DEMO"]
    self.demo_regions = ["DEMO"]
    self.real_regions = ["REAL"]
    return await orig_connect(self, *a, **kw)
WebsocketClient.connect = patched_connect

# Patch on_message to log ALL messages
orig_on_message = WebsocketClient.on_message
async def patched_on_message(self, message):
    if isinstance(message, bytes):
        try:
            decoded = message.decode("utf-8")
            data = json.loads(decoded)
            msg_type = data[0] if isinstance(data, list) and data else "unknown"
            print(f"  BINARY type={msg_type} len={len(decoded)}")
            # Handle loadHistoryPeriodFast directly
            if msg_type == "loadHistoryPeriodFast":
                payload = data[1] if len(data) > 1 else data
                if isinstance(payload, dict):
                    self.api.history_data = payload
                    self.api._history_data_event.set()
                    candle_count = len(payload.get("data", []))
                    print(f"  >>> loadHistoryPeriodFast: {candle_count} candles")
        except:
            print(f"  BINARY raw {len(message)} bytes (undecodable)")
        return
    # Log text messages
    msg_preview = message[:150] if isinstance(message, str) else str(message)[:150]
    if not message.startswith("0{") and message != "2" and not message.startswith("40{"):
        print(f"  TEXT: {msg_preview}")
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
        print("Subscribing EURUSD_otc period=60...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(3)

        print("Getting candles...")
        try:
            candles = api.get_historical_candles("EURUSD_otc", period=60, count_request=1)
            if candles:
                print(f"\nGOT {len(candles)} CANDLES!")
                for c in candles[-3:]:
                    print(c)
            else:
                print("No candles returned")
        except Exception as e:
            print(f"Error: {e}")

    api.disconnect_websocket()

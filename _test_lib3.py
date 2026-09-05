import sys, time, logging
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO)
from pocketoptionapi import PocketOption
from pocketoptionapi.ws.client import WebSocketClient

# Exact SSID from browser
EXACT_SSID = '42["auth",{"sessionToken":"9aca9c3cc8c5e85691bbded020e0c83e","uid":"140064076","lang":"ru","currentUrl":"cabinet/demo-quick-high-low","isChart":1}]'

# Monkey-patch to send exact SSID
original_build = WebSocketClient._build_auth_message
def patched_build(self):
    return EXACT_SSID
WebSocketClient._build_auth_message = patched_build

api = PocketOption(EXACT_SSID)
ok, err = api.connect()
print(f"Connect: ok={ok}, err={err}")
if ok:
    for i in range(50):
        if api.check_connect():
            print(f"Connected after {i*0.1:.1f}s")
            break
        time.sleep(0.1)
    else:
        print("Not connected after 5s")

    if api.check_connect():
        print("Subscribing EURUSD_otc...")
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(3)
        try:
            candles = api.get_historical_candles("EURUSD_otc", period=60)
            if candles is not None:
                print(f"Got {len(candles)} candles!")
                print(candles.tail(3).to_string())
            else:
                print("No candles")
        except Exception as e:
            print(f"Error: {e}")
    api.disconnect()

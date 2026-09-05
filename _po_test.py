import sys, time, os
sys.stdout.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("Paste fresh SSID:")
ssid = input("> ").strip()
if not ssid:
    print("Empty SSID")
    sys.exit(1)

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
        print("Subscribing EURUSD_otc period=60...")
        ok_sub = api.subscribe("EURUSD_otc", period=60)
        print(f"Subscribe: {ok_sub}")
        time.sleep(2)

        print("Getting candles...")
        try:
            candles = api.get_historical_candles("EURUSD_otc", period=60, count_request=1)
            if candles:
                print(f"GOT {len(candles)} CANDLES!")
                if isinstance(candles, list):
                    for c in candles[-3:]:
                        print(c)
                elif hasattr(candles, 'tail'):
                    print(candles.tail(3).to_string())
            else:
                print("No candles returned")
        except Exception as e:
            print(f"Candles error: {e}")
            import traceback
            traceback.print_exc()

    api.disconnect_websocket()

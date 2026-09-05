import sys, time, os
sys.stdout.reconfigure(encoding="utf-8")

# Disable proxy for PO connections
os.environ["NO_PROXY"] = "demo-api-eu.po.market,api-eu.po.market,try-demo-eu.po.market"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

print("1) Open PO in browser")
print("2) Refresh page (F5)")
print("3) F12 -> Network -> Socket -> Messages")
print("4) Find 42[\"auth\",{...}] and copy FULL value")
print("5) Paste below:")
print()

ssid = input("SSID: ").strip()
if not ssid:
    print("Empty SSID")
    sys.exit(1)

print(f"\nSSID length: {len(ssid)}")

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
    for i in range(50):
        if api.check_connect():
            print(f"Connected! ({i*0.1:.1f}s)")
            break
        time.sleep(0.1)
    else:
        print("Timeout")

    if api.check_connect():
        api.subscribe("EURUSD_otc", period=60)
        time.sleep(3)
        try:
            candles = api.get_historical_candles("EURUSD_otc", period=60)
            if candles is not None:
                print(f"\n=== GOT {len(candles)} CANDLES ===")
                print(candles.tail(5).to_string())
            else:
                print("No candles")
        except Exception as e:
            print(f"Error: {e}")
    api.disconnect()

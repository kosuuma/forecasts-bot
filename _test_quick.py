"""
Quick PO connection test.
1. Refresh PO page in browser
2. Copy fresh SSID from Network -> Socket -> Messages
3. Run this script and paste SSID when asked
"""
import sys, time, asyncio, aiohttp, json
sys.stdout.reconfigure(encoding="utf-8")

async def test_ssid(ssid_str):
    url = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
    headers = {"Origin": "https://po.trade/"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(url) as ws:
            auth_sent = False
            for _ in range(30):
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if msg.data.startswith("0") and not msg.data.startswith("40"):
                        await ws.send_str("40")
                    elif msg.data.startswith("40") and not auth_sent:
                        await ws.send_str(ssid_str)
                        auth_sent = True
                        print("  Auth sent...")
                    elif msg.data == "2":
                        await ws.send_str("3")
                    elif msg.data == "41":
                        print("  FAIL: server rejected (41)")
                        return False
                    elif "user_init" in msg.data:
                        print(f"  SUCCESS: {msg.data[:200]}")
                        return True
                    else:
                        print(f"  msg: {msg.data[:120]}")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    print("  WS closed")
                    return False
            print("  Timeout")
            return False

print("=== PO Quick Test ===")
print("Paste your fresh SSID (the full 42[\"auth\",{...}] string):")
ssid = input("> ").strip()
if not ssid.startswith("42["):
    print("ERROR: SSID must start with 42[")
    sys.exit(1)

print(f"\nTesting...")
result = asyncio.run(test_ssid(ssid))
print(f"\nResult: {'OK' if result else 'FAILED'}")

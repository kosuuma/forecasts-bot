"""Тест подключения к Pocket Option WebSocket."""
import asyncio
import sys
sys.path.insert(0, r"D:\AI PROJECTS\forecasts bot")

from pocket_option import PocketOptionClient


async def test():
    uid = 140064076
    secret = "9aca9c3cc8e85691bbded020e0c83e"

    client = PocketOptionClient(uid, secret, is_demo=True)
    print("Подключение к PO...")
    ok = await client.connect()

    if not ok:
        print("Ошибка подключения!")
        return

    print("Подключено! Запрашиваю свечи EURUSD_otc 1m...")
    df = await client.get_candles("EURUSD_otc", "1m", 200)

    if df is not None:
        print(f"Получено {len(df)} свечей")
        print(df.tail(5))
    else:
        print("Не удалось получить свечи")

    await client.disconnect()
    print("Отключено")


asyncio.run(test())

"""
Конфигурация бота: загрузка переменных окружения и общие константы.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

# --- Pocket Option ---
PO_SSID = os.getenv("PO_SSID", "")
PO_IS_DEMO = os.getenv("PO_IS_DEMO", "1") == "1"

# Data source: "binance" or "pocket_option"
DATA_SOURCE = os.getenv("DATA_SOURCE", "binance")

# --- Биржа и данные ---
DEFAULT_EXCHANGE = os.getenv("DEFAULT_EXCHANGE", "binance")
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))
DB_PATH = os.getenv("DB_PATH", "signals.db")

# Кэш свечей и тикеров, чтобы не спамить API (секунды)
CACHE_TTL_SECONDS = 30

# --- Отслеживаемые пары (можно расширять через /pairs) ---
DEFAULT_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "LTCUSDT", "TRXUSDT", "ATOMUSDT", "NEARUSDT",
    "ETCUSDT", "FILUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
]

# Пары Pocket Option
PO_PAIRS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
    "EURGBP_otc", "EURJPY_otc", "GBPJPY_otc", "USDCAD_otc",
    "USDCHF_otc", "NZDUSD_otc",
    "BTCUSD_otc", "ETHUSD_otc",
]

# --- Таймфреймы ---
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]
DEFAULT_TIMEFRAME = "5m"

# Иерархия таймфреймов: каждый TF → его "старший" TF
TF_HIERARCHY = {
    "1m": "5m",
    "5m": "15m",
    "15m": "1h",
    "1h": "4h",
    "4h": None,  # 4h — старший, нет выше
}

# --- Пороговые значения индикаторов ---
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2

EMA_PERIODS = (9, 21, 50, 200)

STOCH_RSI_PERIOD = 14

ATR_PERIOD = 14
# Минимальная волатильность (ATR / цена, в %) для выдачи сигнала
ATR_MIN_PCT = 0.02

VOLUME_SPIKE_MULTIPLIER = 1.2  # объём выше среднего в X раз считается аномальным

# --- Funding Rate ---
FUNDING_RATE_BULLISH = -0.01   # funding < -0.01% = шортит рынок → бонус для UP
FUNDING_RATE_BEARISH = 0.01    # funding > +0.01% = лонгит рынок → бонус для DOWN
FUNDING_RATE_EXTREME = 0.05    # экстремальный funding = +1 бонус к скору

# --- Orderbook ---
ORDERBOOK_DEPTH = 20             # количество уровней стакана для анализа
ORDERBOOK_BID_ASK_RATIO = 1.5   # бычий сигнал: bid/ask > 1.5
ORDERBOOK_BEARISH_RATIO = 0.67  # медвежий сигнал: bid/ask < 0.67
ORDERBOOK_SPREAD_MAX = 0.5      # максимальный spread в % (иначе штраф)

# Резкое движение цены для отдельного алерта (% за 5 минут)
PRICE_SPIKE_PCT = 3.0

# --- Логика силы сигнала ---
# Всего 10 индикаторов: RSI, MACD, BB, EMA, Volume, S/R, Funding, Orderbook, FearGreed, LongShort
MIN_CONFIRMATIONS_TO_SEND = 3  # минимум 3 индикатора для сигнала
STRONG_THRESHOLD = 5           # 5-10 индикаторов = Strong
MEDIUM_THRESHOLD = 3           # 3-4 индикатора = Medium

# Rate limiting: не чаще одного сигнала на пару за X минут
SIGNAL_COOLDOWN_MINUTES = 5

# --- TP/SL на основе ATR ---
TP_ATR_MULTIPLIER = 2.0    # Take Profit = entry ± ATR * 2
SL_ATR_MULTIPLIER = 1.5    # Stop Loss  = entry ∓ ATR * 1.5
SIGNAL_EXPIRY_CANDLES = 3  # время жизни сигнала = timeframe * N свечей

# Список бирж и их REST-эндпоинтов для получения klines/тикеров
EXCHANGES = {
    "binance": {
        "klines_url": "https://api.binance.com/api/v3/klines",
        "ticker_24h_url": "https://api.binance.com/api/v3/ticker/24hr",
        "funding_url": "https://fapi.binance.com/fapi/v1/premiumIndex",
        "depth_url": "https://api.binance.com/api/v3/depth",
    },
    "bybit": {
        "klines_url": "https://api.bybit.com/v5/market/kline",
        "ticker_24h_url": "https://api.bybit.com/v5/market/tickers",
        "funding_url": "https://api.bybit.com/v5/market/funding/history",
        "depth_url": "https://api.bybit.com/v5/market/orderbook",
    },
    "okx": {
        "klines_url": "https://www.okx.com/api/v5/market/candles",
        "ticker_24h_url": "https://www.okx.com/api/v5/market/ticker",
        "funding_url": "https://www.okx.com/api/v5/public/funding-rate",
        "depth_url": "https://www.okx.com/api/v5/market/books",
    },
}

LOG_FILE = "bot.log"

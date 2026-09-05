"""
Работа с базой данных SQLite: подписчики, история сигналов, статистика.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

import config

logger = logging.getLogger("database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id INTEGER PRIMARY KEY,
    timeframe TEXT DEFAULT '5m',
    min_confidence INTEGER DEFAULT 60,
    frequency_minutes INTEGER DEFAULT 5,
    subscribed INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signals_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    strength_label TEXT NOT NULL,
    strength_pct INTEGER NOT NULL,
    price REAL NOT NULL,
    tp_price REAL,
    sl_price REAL,
    atr REAL,
    expiry_minutes INTEGER DEFAULT 15,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    outcome TEXT DEFAULT 'pending'  -- pending / win / loss / expired
);

CREATE TABLE IF NOT EXISTS pairs (
    symbol TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals_history(symbol, created_at);
"""


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        # Заполняем таблицу пар значениями по умолчанию, если пусто
        cursor = await self._conn.execute("SELECT COUNT(*) FROM pairs")
        row = await cursor.fetchone()
        if row[0] == 0:
            await self._conn.executemany(
                "INSERT OR IGNORE INTO pairs (symbol, enabled) VALUES (?, 1)",
                [(p,) for p in config.DEFAULT_PAIRS],
            )
            await self._conn.commit()
        logger.info(f"База данных подключена: {self.path}")

    async def close(self):
        if self._conn:
            await self._conn.close()

    # --- Подписчики ---
    async def subscribe(self, chat_id: int, timeframe: str = None, min_confidence: int = None):
        await self._conn.execute(
            """INSERT INTO subscribers (chat_id, timeframe, min_confidence, subscribed)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(chat_id) DO UPDATE SET subscribed = 1""",
            (chat_id, timeframe or config.DEFAULT_TIMEFRAME, min_confidence or 60),
        )
        await self._conn.commit()

    async def unsubscribe(self, chat_id: int):
        await self._conn.execute(
            "UPDATE subscribers SET subscribed = 0 WHERE chat_id = ?", (chat_id,)
        )
        await self._conn.commit()

    async def update_settings(self, chat_id: int, **kwargs):
        """Обновляет настройки пользователя (timeframe, min_confidence, frequency_minutes)."""
        if not kwargs:
            return
        # Убеждаемся что пользователь существует
        await self._conn.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)", (chat_id,)
        )
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [chat_id]
        await self._conn.execute(
            f"UPDATE subscribers SET {set_clause} WHERE chat_id = ?", values
        )
        await self._conn.commit()

    async def get_settings(self, chat_id: int) -> dict:
        cursor = await self._conn.execute(
            "SELECT timeframe, min_confidence, frequency_minutes, subscribed FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {
                "timeframe": config.DEFAULT_TIMEFRAME,
                "min_confidence": 60,
                "frequency_minutes": config.SCAN_INTERVAL_MINUTES,
                "subscribed": False,
            }
        return {
            "timeframe": row[0],
            "min_confidence": row[1],
            "frequency_minutes": row[2],
            "subscribed": bool(row[3]),
        }

    async def get_active_subscribers(self) -> list:
        cursor = await self._conn.execute(
            "SELECT chat_id, timeframe, min_confidence FROM subscribers WHERE subscribed = 1"
        )
        rows = await cursor.fetchall()
        return [{"chat_id": r[0], "timeframe": r[1], "min_confidence": r[2]} for r in rows]

    # --- История сигналов ---
    async def save_signal(self, signal) -> int:
        cursor = await self._conn.execute(
            """INSERT INTO signals_history
               (symbol, timeframe, direction, strength_label, strength_pct,
                price, tp_price, sl_price, atr, expiry_minutes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal.symbol, signal.timeframe, signal.direction, signal.strength_label,
             signal.strength_pct, signal.price, signal.tp_price, signal.sl_price,
             signal.atr, signal.expiry_minutes),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_last_signal_time(self, symbol: str) -> Optional[datetime]:
        """Для rate limiting: время последнего сигнала по паре."""
        cursor = await self._conn.execute(
            "SELECT created_at FROM signals_history WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
            (symbol,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")

    async def get_recent_signals(self, limit: int = 10) -> list:
        cursor = await self._conn.execute(
            """SELECT symbol, timeframe, direction, strength_label, strength_pct, price, created_at, outcome
               FROM signals_history ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        cols = ["symbol", "timeframe", "direction", "strength_label", "strength_pct", "price", "created_at", "outcome"]
        result = []
        for r in rows:
            d = dict(zip(cols, r))
            # Конвертируем UTC в местное время (Москва UTC+3)
            if d["created_at"]:
                from datetime import datetime, timedelta
                utc_time = datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S")
                local_time = utc_time + timedelta(hours=3)
                d["created_at"] = local_time.strftime("%d.%m %H:%M")
            result.append(d)
        return result

    async def update_outcome(self, signal_id: int, outcome: str):
        await self._conn.execute(
            "UPDATE signals_history SET outcome = ?, resolved_at = datetime('now') WHERE id = ?",
            (outcome, signal_id),
        )
        await self._conn.commit()

    async def get_pending_signals(self) -> list:
        """Сигналы, ожидающие определения исхода (win/loss/expired)."""
        cursor = await self._conn.execute(
            """SELECT id, symbol, direction, price, tp_price, sl_price,
                      expiry_minutes, created_at
               FROM signals_history
               WHERE outcome = 'pending'""",
        )
        rows = await cursor.fetchall()
        return [{"id": r[0], "symbol": r[1], "direction": r[2], "price": r[3],
                 "tp_price": r[4], "sl_price": r[5], "expiry_minutes": r[6],
                 "created_at": r[7]} for r in rows]

    # --- Статистика ---
    async def get_stats(self, days: int = 7) -> dict:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = await self._conn.execute(
            """SELECT outcome, COUNT(*) FROM signals_history
               WHERE created_at >= ? AND outcome != 'pending'
               GROUP BY outcome""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        counts = {outcome: cnt for outcome, cnt in rows}
        wins = counts.get("win", 0)
        losses = counts.get("loss", 0)
        expired = counts.get("expired", 0)
        total = wins + losses
        winrate = round(wins / total * 100, 1) if total else 0.0

        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM signals_history WHERE created_at >= ?", (cutoff,)
        )
        total_signals = (await cursor.fetchone())[0]

        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM signals_history WHERE created_at >= ? AND outcome = 'pending'",
            (cutoff,),
        )
        pending = (await cursor.fetchone())[0]

        return {
            "days": days,
            "total_signals": total_signals,
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "pending": pending,
            "winrate": winrate,
        }

    async def get_streak(self, days: int = 7) -> dict:
        """Последовательность побед/поражений (streak)."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = await self._conn.execute(
            """SELECT outcome FROM signals_history
               WHERE created_at >= ? AND outcome IN ('win', 'loss')
               ORDER BY created_at DESC""",
            (cutoff,),
        )
        rows = [r[0] for r in await cursor.fetchall()]

        if not rows:
            return {"type": "—", "count": 0}

        current_type = rows[0]
        count = 0
        for outcome in rows:
            if outcome == current_type:
                count += 1
            else:
                break

        return {"type": current_type, "count": count}

    async def get_stats_by_timeframe(self, days: int = 7) -> list:
        """Статистика по таймфреймам."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = await self._conn.execute(
            """SELECT timeframe,
                      SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                      SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                      COUNT(*) as total
               FROM signals_history
               WHERE created_at >= ? AND outcome != 'pending'
               GROUP BY timeframe
               ORDER BY total DESC""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        result = []
        for tf, wins, losses, total in rows:
            resolved = wins + losses
            winrate = round(wins / resolved * 100, 1) if resolved else 0.0
            result.append({"timeframe": tf, "wins": wins, "losses": losses,
                           "total": total, "winrate": winrate})
        return result

    async def get_stats_by_pair(self, days: int = 7) -> list:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = await self._conn.execute(
            """SELECT symbol,
                      SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                      SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses
               FROM signals_history
               WHERE created_at >= ? AND outcome != 'pending'
               GROUP BY symbol
               ORDER BY (wins + losses) DESC""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        result = []
        for symbol, wins, losses in rows:
            total = wins + losses
            winrate = round(wins / total * 100, 1) if total else 0.0
            result.append({"symbol": symbol, "wins": wins, "losses": losses, "winrate": winrate})
        return result

    # --- Пары ---
    async def get_enabled_pairs(self) -> list:
        cursor = await self._conn.execute("SELECT symbol FROM pairs WHERE enabled = 1")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_all_pairs(self) -> list:
        cursor = await self._conn.execute("SELECT symbol, enabled FROM pairs")
        rows = await cursor.fetchall()
        return [{"symbol": r[0], "enabled": bool(r[1])} for r in rows]

    async def toggle_pair(self, symbol: str, enabled: bool):
        await self._conn.execute(
            "INSERT INTO pairs (symbol, enabled) VALUES (?, ?) "
            "ON CONFLICT(symbol) DO UPDATE SET enabled = ?",
            (symbol, int(enabled), int(enabled)),
        )
        await self._conn.commit()

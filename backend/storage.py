import sqlite3
from backend.models import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_index_price REAL NOT NULL,
    entry_futures_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target REAL NOT NULL,
    rr REAL NOT NULL,
    sl_method TEXT NOT NULL
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def insert_signal(conn: sqlite3.Connection, signal: Signal) -> None:
    conn.execute(
        """INSERT INTO signals
           (timestamp, timeframe, direction, entry_index_price, entry_futures_price,
            stop_loss, target, rr, sl_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal.timestamp.isoformat(),
            signal.timeframe,
            signal.direction,
            signal.entry_index_price,
            signal.entry_futures_price,
            signal.stop_loss,
            signal.target,
            signal.rr,
            signal.sl_method,
        ),
    )
    conn.commit()


def get_recent_signals(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    cursor = conn.execute(
        "SELECT timestamp, timeframe, direction, entry_index_price, entry_futures_price, "
        "stop_loss, target, rr, sl_method FROM signals ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

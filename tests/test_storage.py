from datetime import datetime
from backend.models import Signal
from backend.storage import init_db, insert_signal, get_recent_signals


def make_signal(direction="BUY"):
    return Signal(
        timestamp=datetime(2026, 7, 1, 9, 20),
        timeframe="1m",
        direction=direction,
        entry_index_price=100.0,
        entry_futures_price=101.0,
        stop_loss=95.0,
        target=115.0,
        rr=3.0,
        sl_method="atr",
    )


def test_insert_and_fetch_signal(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    insert_signal(conn, make_signal())
    rows = get_recent_signals(conn)
    assert len(rows) == 1
    assert rows[0]["direction"] == "BUY"
    assert rows[0]["stop_loss"] == 95.0


def test_get_recent_signals_respects_limit_and_order(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    insert_signal(conn, make_signal("BUY"))
    insert_signal(conn, make_signal("SELL"))
    rows = get_recent_signals(conn, limit=1)
    assert len(rows) == 1
    assert rows[0]["direction"] == "SELL"

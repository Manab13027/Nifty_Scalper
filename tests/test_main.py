import importlib
import sys
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.models import Candle


def test_ws_sends_history_frames_on_connect(monkeypatch, tmp_path):
    # backend.main creates its sqlite connection at import time from DB_PATH,
    # so set the env var and force a fresh import to guarantee it takes effect
    # (another test in the session may have already imported the module).
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    sys.modules.pop("backend.main", None)
    main = importlib.import_module("backend.main")

    # Keep the lifespan backfill quiet and fast: no real Dhan API call.
    # backfill() already tolerates this failure gracefully.
    def _fail_fast(self, *args, **kwargs):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(main.DhanClient, "fetch_intraday_candles", _fail_fast)

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws") as ws:
            frames = [ws.receive_json() for _ in range(4)]

    types = {f["type"] for f in frames}
    timeframes = {f["timeframe"] for f in frames}
    assert types == {"history"}
    assert timeframes == {"1m", "15m", "1h", "day"}


def test_backtest_endpoint_runs_strategy_over_fetched_range(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    sys.modules.pop("backend.main", None)
    main = importlib.import_module("backend.main")

    # Crossover fixture (same family as test_signals.py): downtrend then jump,
    # then a continued rally so the 1:3 target resolves as a win.
    base = datetime(2026, 7, 1, 9, 15)
    closes = [110 - i for i in range(25)] + [200, 210, 220, 260, 320, 400, 500, 600]
    fake_candles = [
        Candle(base + timedelta(minutes=i), c, c + 1, c - 1, c, 100)
        for i, c in enumerate(closes)
    ]

    def _fake_fetch(self, *args, **kwargs):
        return fake_candles

    monkeypatch.setattr(main.DhanClient, "fetch_intraday_candles", _fake_fetch)

    with TestClient(main.app) as client:
        resp = client.get(
            "/backtest",
            params={"from_date": "2026-07-01", "to_date": "2026-07-01", "timeframe": "1m"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["trades"] == 1
    assert body["stats"]["wins"] == 1
    assert body["stats"]["win_rate"] == 1.0
    assert body["trades"][0]["direction"] == "BUY"
    assert body["trades"][0]["outcome"] == "win"
    assert len(body["candles"]) == len(fake_candles)


def test_backtest_endpoint_rejects_bad_timeframe(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    sys.modules.pop("backend.main", None)
    main = importlib.import_module("backend.main")

    def _fail_fast(self, *args, **kwargs):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(main.DhanClient, "fetch_intraday_candles", _fail_fast)

    with TestClient(main.app) as client:
        resp = client.get(
            "/backtest",
            params={"from_date": "2026-07-01", "to_date": "2026-07-01", "timeframe": "5m"},
        )
    assert resp.status_code == 400

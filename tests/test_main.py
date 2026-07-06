import importlib
import sys

from fastapi.testclient import TestClient


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

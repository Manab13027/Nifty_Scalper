import pytest
from unittest.mock import MagicMock
from backend.dhan_client import DhanClient


def test_fetch_intraday_candles_parses_response(monkeypatch):
    fake_response = {
        "data": {
            "timestamp": [1751350500, 1751350560],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1200],
        }
    }
    mock_sdk = MagicMock()
    mock_sdk.intraday_minute_data.return_value = fake_response
    monkeypatch.setattr("backend.dhan_client.dhanhq", lambda *a, **k: mock_sdk)

    client = DhanClient("client_id", "access_token")
    candles = client.fetch_intraday_candles("13", "IDX_I", "INDEX", "2026-07-01", "2026-07-01")

    assert len(candles) == 2
    assert candles[0].open == 100.0
    assert candles[1].close == 102.0


def test_fetch_intraday_candles_raises_on_api_failure(monkeypatch):
    fake_response = {"status": "failure", "remarks": "Invalid access token", "data": ""}
    mock_sdk = MagicMock()
    mock_sdk.intraday_minute_data.return_value = fake_response
    monkeypatch.setattr("backend.dhan_client.dhanhq", lambda *a, **k: mock_sdk)

    client = DhanClient("client_id", "access_token")
    with pytest.raises(RuntimeError, match="Invalid access token"):
        client.fetch_intraday_candles("13", "IDX_I", "INDEX", "2026-07-01", "2026-07-01")

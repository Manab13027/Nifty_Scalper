import pytest
from datetime import date
from unittest.mock import MagicMock
from backend.dhan_client import DhanClient, parse_nifty_fut_security_id


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


# Fixture mirroring Dhan's scrip-master CSV shape (relevant columns only):
# NIFTY Jul + Aug futures, a BANKNIFTY future (must be excluded), an expired
# NIFTY June future, and a NIFTY option (OPTIDX — must be excluded).
SCRIP_MASTER_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE
NSE,D,58072,FUTIDX,0,NIFTY-Aug2026-FUT,65.0,NIFTY AUG FUT,2026-08-25 14:30:00
NSE,D,61093,FUTIDX,0,NIFTY-Jul2026-FUT,65.0,NIFTY JUL FUT,2026-07-28 14:30:00
NSE,D,99999,FUTIDX,0,BANKNIFTY-Jul2026-FUT,30.0,BANKNIFTY JUL FUT,2026-07-28 14:30:00
NSE,D,11111,FUTIDX,0,NIFTY-Jun2026-FUT,65.0,NIFTY JUN FUT,2026-06-24 14:30:00
NSE,D,22222,OPTIDX,0,NIFTY-Jul2026-25000-CE,65.0,NIFTY 25000 CALL,2026-07-28 14:30:00
"""


def test_parse_nifty_fut_picks_nearest_unexpired_contract():
    assert parse_nifty_fut_security_id(SCRIP_MASTER_CSV, today=date(2026, 7, 9)) == "61093"


def test_parse_nifty_fut_includes_expiry_day_itself():
    assert parse_nifty_fut_security_id(SCRIP_MASTER_CSV, today=date(2026, 7, 28)) == "61093"


def test_parse_nifty_fut_rolls_to_next_month_after_expiry():
    assert parse_nifty_fut_security_id(SCRIP_MASTER_CSV, today=date(2026, 7, 29)) == "58072"


def test_parse_nifty_fut_returns_none_when_no_contract_available():
    assert parse_nifty_fut_security_id(SCRIP_MASTER_CSV, today=date(2026, 9, 1)) is None


def test_parse_nifty_fut_ignores_malformed_rows():
    csv_text = SCRIP_MASTER_CSV + "NSE,D,33333,FUTIDX,0,NIFTY-BadDate-FUT,65.0,NIFTY BAD FUT,not-a-date\n"
    assert parse_nifty_fut_security_id(csv_text, today=date(2026, 7, 9)) == "61093"

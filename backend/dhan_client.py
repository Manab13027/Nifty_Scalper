import csv
import io
from datetime import date, datetime

import httpx
from dhanhq import dhanhq
from backend.models import Candle

NIFTY_INDEX_SECURITY_ID = "13"
NIFTY_INDEX_EXCHANGE_SEGMENT = "IDX_I"
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"


def parse_nifty_fut_security_id(csv_text: str, today: date | None = None) -> str | None:
    """Find the current-month NIFTY index futures security_id in Dhan's scrip master.

    Picks the NIFTY FUTIDX contract with the nearest expiry on or after `today`
    (a contract is tradeable through its expiry day). Trading symbols look like
    "NIFTY-Jul2026-FUT"; the "NIFTY-" prefix match excludes BANKNIFTY/FINNIFTY/
    MIDCPNIFTY etc., and the FUTIDX filter excludes options. Returns None if no
    unexpired contract is found. Malformed rows are skipped.
    """
    if today is None:
        today = date.today()
    best: tuple[date, str] | None = None
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("SEM_INSTRUMENT_NAME") != "FUTIDX":
            continue
        symbol = row.get("SEM_TRADING_SYMBOL", "")
        if not symbol.startswith("NIFTY-"):
            continue
        try:
            expiry = datetime.strptime(row["SEM_EXPIRY_DATE"][:10], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if expiry < today:
            continue
        security_id = row.get("SEM_SMST_SECURITY_ID", "").strip()
        if not security_id:
            continue
        if best is None or expiry < best[0]:
            best = (expiry, security_id)
    return best[1] if best else None


def resolve_nifty_fut_security_id() -> str | None:
    """Download Dhan's public scrip master (~10 MB, no auth) and resolve the
    current NIFTY futures security_id. Returns None on any failure — callers
    fall back to using the index price as the futures reference."""
    response = httpx.get(SCRIP_MASTER_URL, timeout=30.0)
    response.raise_for_status()
    return parse_nifty_fut_security_id(response.text)


class DhanClient:
    def __init__(self, client_id: str, access_token: str):
        self._dhan = dhanhq(client_id, access_token)

    def fetch_intraday_candles(
        self, security_id: str, exchange_segment: str, instrument_type: str,
        from_date: str, to_date: str,
    ) -> list[Candle]:
        response = self._dhan.intraday_minute_data(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            from_date=from_date,
            to_date=to_date,
        )
        if response.get("status") == "failure":
            raise RuntimeError(f"Dhan API error: {response.get('remarks')}")
        data = response.get("data", response)
        candles = []
        for i in range(len(data["open"])):
            candles.append(Candle(
                timestamp=datetime.fromtimestamp(data["timestamp"][i]),
                open=data["open"][i],
                high=data["high"][i],
                low=data["low"][i],
                close=data["close"][i],
                volume=data["volume"][i],
            ))
        return candles

from datetime import datetime
from dhanhq import dhanhq
from backend.models import Candle

NIFTY_INDEX_SECURITY_ID = "13"
NIFTY_INDEX_EXCHANGE_SEGMENT = "IDX_I"


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

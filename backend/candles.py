from datetime import datetime, timedelta
from backend.models import Candle

TIMEFRAME_SECONDS = {
    "1m": 60,
    "15m": 900,
    "1h": 3600,
    "day": 86400,
}


class CandleBuilder:
    def __init__(self, timeframe: str):
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        self.timeframe = timeframe
        self._bucket_seconds = TIMEFRAME_SECONDS[timeframe]
        self.candles: list[Candle] = []
        self._current_bucket_start: datetime | None = None

    def _bucket_start(self, ts: datetime) -> datetime:
        midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.timeframe == "day":
            return midnight
        seconds_since_midnight = (ts - midnight).total_seconds()
        offset = seconds_since_midnight - (seconds_since_midnight % self._bucket_seconds)
        return midnight + timedelta(seconds=offset)

    def add_tick(self, timestamp: datetime, price: float, volume: float = 0.0) -> Candle | None:
        bucket_start = self._bucket_start(timestamp)
        closed: Candle | None = None
        if self._current_bucket_start is None:
            self._current_bucket_start = bucket_start
            self.candles.append(Candle(bucket_start, price, price, price, price, volume))
        elif bucket_start != self._current_bucket_start:
            closed = self.candles[-1]
            self._current_bucket_start = bucket_start
            self.candles.append(Candle(bucket_start, price, price, price, price, volume))
        else:
            live = self.candles[-1]
            live.high = max(live.high, price)
            live.low = min(live.low, price)
            live.close = price
            live.volume += volume
        return closed

    def seed(self, candles: list[Candle]) -> None:
        self.candles = list(candles)
        if self.candles:
            self._current_bucket_start = self._bucket_start(self.candles[-1].timestamp)


def resample(candles: list[Candle], timeframe: str) -> list[Candle]:
    """Resample 1-minute OHLCV candles into a coarser timeframe."""
    builder = CandleBuilder(timeframe)
    result: list[Candle] = []
    for c in candles:
        bucket_start = builder._bucket_start(c.timestamp)
        if builder._current_bucket_start is None or bucket_start != builder._current_bucket_start:
            if builder.candles:
                result.append(builder.candles[-1])
            builder._current_bucket_start = bucket_start
            builder.candles.append(Candle(bucket_start, c.open, c.high, c.low, c.close, c.volume))
        else:
            live = builder.candles[-1]
            live.high = max(live.high, c.high)
            live.low = min(live.low, c.low)
            live.close = c.close
            live.volume += c.volume
    if builder.candles:
        result.append(builder.candles[-1])
    return result

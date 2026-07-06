from dataclasses import replace
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
        # Bucketed relative to midnight of the calendar day (not unix epoch),
        # so market-open-aligned boundaries (9:15, 9:30, 9:45 IST) land exactly.
        midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.timeframe == "day":
            return midnight
        seconds_since_midnight = (ts - midnight).total_seconds()
        offset = seconds_since_midnight - (seconds_since_midnight % self._bucket_seconds)
        return midnight + timedelta(seconds=offset)

    def add_tick(self, timestamp: datetime, price: float, volume: float = 0.0) -> Candle | None:
        return self._merge(timestamp, price, price, price, price, volume)

    def merge_candle(self, candle: Candle) -> Candle | None:
        """Merge a fully-formed OHLCV candle (e.g. from resample) into this builder."""
        return self._merge(candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume)

    def _merge(self, timestamp: datetime, o: float, h: float, l: float, c: float, v: float) -> Candle | None:
        bucket_start = self._bucket_start(timestamp)
        closed: Candle | None = None
        if self._current_bucket_start is None:
            self._current_bucket_start = bucket_start
            self.candles.append(Candle(bucket_start, o, h, l, c, v))
        elif bucket_start != self._current_bucket_start:
            closed = self.candles[-1]
            self._current_bucket_start = bucket_start
            self.candles.append(Candle(bucket_start, o, h, l, c, v))
        else:
            live = self.candles[-1]
            live.high = max(live.high, h)
            live.low = min(live.low, l)
            live.close = c
            live.volume += v
        return closed

    def seed(self, candles: list[Candle]) -> None:
        self.candles = [replace(c) for c in candles]
        if self.candles:
            self._current_bucket_start = self._bucket_start(self.candles[-1].timestamp)


def resample(candles: list[Candle], timeframe: str) -> list[Candle]:
    """Resample 1-minute OHLCV candles into a coarser timeframe."""
    builder = CandleBuilder(timeframe)
    result: list[Candle] = []
    for c in candles:
        closed = builder.merge_candle(c)
        if closed:
            result.append(closed)
    if builder.candles:
        result.append(builder.candles[-1])
    return result

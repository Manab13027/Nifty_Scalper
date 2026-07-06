from datetime import datetime, timedelta
from backend.candles import CandleBuilder, resample
from backend.models import Candle


def test_add_tick_starts_new_candle_on_first_tick():
    builder = CandleBuilder("1m")
    closed = builder.add_tick(datetime(2026, 7, 1, 9, 15, 5), 100.0, 10)
    assert closed is None
    assert len(builder.candles) == 1
    assert builder.candles[0].open == 100.0


def test_add_tick_updates_live_candle_within_same_bucket():
    builder = CandleBuilder("1m")
    builder.add_tick(datetime(2026, 7, 1, 9, 15, 5), 100.0, 10)
    builder.add_tick(datetime(2026, 7, 1, 9, 15, 30), 105.0, 5)
    live = builder.candles[-1]
    assert live.high == 105.0
    assert live.close == 105.0
    assert live.volume == 15


def test_add_tick_closes_candle_when_bucket_changes():
    builder = CandleBuilder("1m")
    builder.add_tick(datetime(2026, 7, 1, 9, 15, 5), 100.0, 10)
    closed = builder.add_tick(datetime(2026, 7, 1, 9, 16, 1), 110.0, 10)
    assert closed is not None
    assert closed.close == 100.0
    assert len(builder.candles) == 2


def test_seed_preloads_historical_candles():
    builder = CandleBuilder("1m")
    historical = [Candle(datetime(2026, 7, 1, 9, 15), 100, 101, 99, 100, 50)]
    builder.seed(historical)
    assert builder.candles == historical


def test_resample_aggregates_1m_candles_into_15m_bucket():
    base = datetime(2026, 7, 1, 9, 15)
    one_min = [
        Candle(base, 100, 102, 98, 101, 10),
        Candle(base + timedelta(minutes=1), 101, 105, 100, 104, 10),
        Candle(base + timedelta(minutes=14), 104, 106, 103, 105, 10),
        Candle(base + timedelta(minutes=15), 105, 108, 104, 107, 10),
    ]
    result = resample(one_min, "15m")
    assert len(result) == 2
    first = result[0]
    assert first.open == 100
    assert first.high == 106
    assert first.low == 98
    assert first.close == 105
    assert first.volume == 30

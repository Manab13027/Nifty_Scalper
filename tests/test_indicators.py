from datetime import datetime, timedelta
from backend.models import Candle
from backend.indicators import ema, session_vwap, atr, swing_low, swing_high


def make_candle(ts, o, h, l, c, v=100):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def test_ema_returns_none_until_period_reached():
    result = ema([1, 2, 3], period=5)
    assert result == [None, None, None]


def test_ema_seeds_with_sma_then_applies_multiplier():
    values = [1, 2, 3, 4, 5, 6]
    result = ema(values, period=3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] == 2.0
    multiplier = 2 / 4
    expected_4 = (4 - 2.0) * multiplier + 2.0
    assert round(result[3], 4) == round(expected_4, 4)


def test_session_vwap_resets_each_day():
    day1 = datetime(2026, 7, 1, 9, 15)
    day2 = datetime(2026, 7, 2, 9, 15)
    candles = [
        make_candle(day1, 100, 110, 90, 100, v=10),
        make_candle(day1 + timedelta(minutes=1), 100, 120, 100, 110, v=10),
        make_candle(day2, 200, 210, 190, 200, v=10),
    ]
    result = session_vwap(candles)
    assert result[0] == (110 + 90 + 100) / 3
    assert result[2] == (210 + 190 + 200) / 3


def test_session_vwap_falls_back_to_cumulative_typical_average_when_no_volume():
    day = datetime(2026, 7, 1, 9, 15)
    candles = [
        make_candle(day, 100, 110, 90, 100, v=0),
        make_candle(day + timedelta(minutes=1), 100, 130, 110, 120, v=0),
    ]
    result = session_vwap(candles)
    typical_1 = (110 + 90 + 100) / 3
    typical_2 = (130 + 110 + 120) / 3
    assert result[0] == typical_1
    assert result[1] == (typical_1 + typical_2) / 2  # cumulative average, not per-candle


def test_atr_returns_none_until_period_plus_one_candles():
    candles = [make_candle(datetime(2026, 7, 1) + timedelta(minutes=i), 100, 105, 95, 100) for i in range(10)]
    result = atr(candles, period=14)
    assert result == [None] * 10


def test_atr_computes_seed_after_enough_candles():
    candles = [make_candle(datetime(2026, 7, 1) + timedelta(minutes=i), 100, 105, 95, 100) for i in range(16)]
    result = atr(candles, period=14)
    assert result[14] is not None
    assert result[14] == 10.0


def test_atr_applies_wilder_recurrence_after_seed():
    base = datetime(2026, 7, 1)
    # 14 candles with TR=10 each (seed), then one more candle with a much larger range
    # so the recurrence step produces a value distinguishable from both the seed
    # and from the new candle's raw TR.
    candles = [make_candle(base + timedelta(minutes=i), 100, 105, 95, 100) for i in range(15)]
    candles.append(make_candle(base + timedelta(minutes=15), 100, 140, 100, 120))
    result = atr(candles, period=14)
    seed = result[14]
    assert seed == 10.0
    tr_15 = max(140 - 100, abs(140 - 100), abs(100 - 100))  # prev_close=100 (candle 14's close)
    expected = (seed * 13 + tr_15) / 14
    assert result[15] == expected
    assert result[15] != seed
    assert result[15] != tr_15


def test_ema_at_exactly_period_values_returns_only_seed():
    values = [1, 2, 3]
    result = ema(values, period=3)
    assert result == [None, None, 2.0]


def test_swing_low_and_high_use_lookback_window():
    candles = [make_candle(datetime(2026, 7, 1) + timedelta(minutes=i), 100, 100 + i, 100 - i, 100) for i in range(12)]
    assert swing_low(candles, lookback=10) == 100 - 11
    assert swing_high(candles, lookback=10) == 100 + 11


def test_swing_low_returns_none_if_not_enough_candles():
    candles = [make_candle(datetime(2026, 7, 1), 100, 105, 95, 100)]
    assert swing_low(candles, lookback=10) is None

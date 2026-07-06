from datetime import datetime, timedelta
from backend.models import Candle
from backend.signals import SignalEngine


def make_series(closes, start=datetime(2026, 7, 1, 9, 15), volume=100):
    candles = []
    for i, close in enumerate(closes):
        ts = start + timedelta(minutes=i)
        candles.append(Candle(ts, close, close + 1, close - 1, close, volume))
    return candles


def test_no_signal_without_enough_history():
    engine = SignalEngine("1m", sl_method="atr")
    candles = make_series([100, 101, 102])
    assert engine.evaluate(candles, futures_price=100.5) is None


def test_buy_signal_on_bullish_crossover_above_vwap():
    engine = SignalEngine("1m", sl_method="atr")
    closes = [110 - i for i in range(25)] + [200, 210, 220]
    candles = make_series(closes)
    signal = None
    for i in range(22, len(candles) + 1):
        signal = engine.evaluate(candles[:i], futures_price=candles[i - 1].close + 5)
        if signal:
            break
    assert signal is not None
    assert signal.direction == "BUY"
    assert signal.stop_loss < signal.entry_index_price
    assert signal.target > signal.entry_index_price
    assert signal.rr == 3.0


def test_signal_does_not_repeat_until_cross_reverses():
    engine = SignalEngine("1m", sl_method="atr")
    closes = [110 - i for i in range(25)] + [200, 210, 220, 225, 230]
    candles = make_series(closes)
    signals = [engine.evaluate(candles[:i], futures_price=candles[i - 1].close) for i in range(22, len(candles) + 1)]
    fired = [s for s in signals if s is not None]
    assert len(fired) == 1


def test_swing_sl_method_places_stop_at_recent_swing_low():
    engine = SignalEngine("1m", sl_method="swing")
    closes = [110 - i for i in range(25)] + [200, 210, 220]
    candles = make_series(closes)
    signal, window = None, None
    for i in range(22, len(candles) + 1):
        signal = engine.evaluate(candles[:i], futures_price=candles[i - 1].close)
        if signal:
            window = candles[:i]
            break
    assert signal is not None
    assert signal.direction == "BUY"
    expected_low = min(c.low for c in window[-10:])
    assert signal.stop_loss == expected_low

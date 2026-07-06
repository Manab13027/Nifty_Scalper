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


def test_rejects_signal_with_zero_atr_stop_loss_distance():
    engine = SignalEngine("1m", sl_method="atr")
    # Flat candles (high == low == close) hold ATR at 0 while completely flat.
    # A large jump (e.g. 100 -> 200) would cross the EMAs *and* immediately
    # push true-range (and therefore ATR) up on that same bar, since ATR
    # includes the current bar's true range in its rolling average — so a
    # sharp jump doesn't actually reach the zero-SL-distance path. A tiny
    # jump, however, still triggers an EMA crossover (any close change does)
    # while keeping ATR-derived SL distance far below MIN_SL_DISTANCE, which
    # is exactly the "effectively zero risk distance" case this guard exists
    # for. Confirmed against the pre-fix code: this fixture produced a real
    # Signal with stop_loss ~= entry (sl_distance ~= 0.0011).
    start = datetime(2026, 7, 1, 9, 15)
    flat_closes = [100] * 25
    candles = [Candle(start + timedelta(minutes=i), c, c, c, c, 100) for i, c in enumerate(flat_closes)]
    tiny_jump = [100.001, 100.002, 100.003]
    candles += [Candle(start + timedelta(minutes=25 + j), c, c, c, c, 100) for j, c in enumerate(tiny_jump)]
    signal = None
    for i in range(22, len(candles) + 1):
        signal = engine.evaluate(candles[:i], futures_price=candles[i - 1].close)
        if signal:
            break
    assert signal is None


def test_custom_risk_reward_changes_target():
    engine = SignalEngine("1m", sl_method="atr", risk_reward=2.0)
    closes = [110 - i for i in range(25)] + [200, 210, 220]
    candles = make_series(closes)
    signal = None
    for i in range(22, len(candles) + 1):
        signal = engine.evaluate(candles[:i], futures_price=candles[i - 1].close)
        if signal:
            break
    assert signal is not None
    assert signal.rr == 2.0
    sl_distance = signal.entry_index_price - signal.stop_loss
    assert abs(signal.target - (signal.entry_index_price + sl_distance * 2.0)) < 1e-9


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

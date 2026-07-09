from datetime import datetime, timedelta
from backend.models import Candle
from backend.backtest import run_backtest, BacktestResult, SimulatedTrade


def make_candle(ts, o, h, l, c, v=100):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def make_series(closes, start=datetime(2026, 7, 1, 9, 15), spread=1.0):
    return [
        make_candle(start + timedelta(minutes=i), c, c + spread, c - spread, c)
        for i, c in enumerate(closes)
    ]


def crossover_series():
    """25-candle downtrend then a sharp jump — same fixture family as
    test_signals.py; produces exactly one BUY crossover."""
    return [110 - i for i in range(25)] + [200, 210, 220]


def test_no_trades_on_flat_data():
    candles = make_series([100] * 40)
    result = run_backtest(candles, timeframe="1m")
    assert result.trades == []
    assert result.total_signals == 0


def test_buy_signal_resolves_as_win_when_target_hit_first():
    closes = crossover_series()
    # continue the rally far enough that the 1:3 target is hit before any SL touch
    closes += [260, 320, 400, 500, 600]
    candles = make_series(closes)
    result = run_backtest(candles, timeframe="1m")
    assert result.total_signals == 1
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction == "BUY"
    assert trade.outcome == "win"
    assert trade.r_multiple == 3.0
    assert trade.exit_price == trade.signal_target
    assert result.wins == 1 and result.losses == 0
    assert result.win_rate == 1.0
    assert result.total_r == 3.0


def test_buy_signal_resolves_as_loss_when_sl_hit_first():
    closes = crossover_series()
    # collapse straight back down through the stop
    closes += [150, 100, 60]
    candles = make_series(closes)
    result = run_backtest(candles, timeframe="1m")
    assert result.total_signals == 1
    trade = result.trades[0]
    assert trade.outcome == "loss"
    assert trade.r_multiple == -1.0
    assert trade.exit_price == trade.signal_stop_loss
    assert result.total_r == -1.0


def test_candle_touching_both_sl_and_target_counts_as_loss():
    closes = crossover_series()
    candles = make_series(closes)
    # one giant candle spanning both SL and target
    last_ts = candles[-1].timestamp
    candles.append(make_candle(last_ts + timedelta(minutes=1), 220, 100000, 0.01, 220))
    result = run_backtest(candles, timeframe="1m")
    assert result.total_signals == 1
    assert result.trades[0].outcome == "loss"


def test_trade_still_open_at_end_of_data():
    candles = make_series(crossover_series())  # signal on last candle, nothing after
    result = run_backtest(candles, timeframe="1m")
    assert result.total_signals == 1
    trade = result.trades[0]
    assert trade.outcome == "open"
    assert trade.r_multiple is None
    assert result.wins == 0 and result.losses == 0
    assert result.win_rate is None  # no closed trades


def test_signals_ignored_while_trade_open():
    # After the first BUY fires and while price meanders between SL and target
    # (no exit), any further signal must not open a second position.
    closes = crossover_series()
    closes += [219, 218, 217, 216, 215, 214, 213, 212, 211, 210,
               209, 208, 207, 206, 205, 204, 203, 202, 201, 200,
               199, 198, 197, 196, 195]
    closes += [400, 420, 440]
    candles = make_series(closes)
    result = run_backtest(candles, timeframe="1m")
    # at most one open position was ever taken regardless of raw signal count
    assert len(result.trades) == 1


def test_custom_engine_params_flow_through():
    closes = crossover_series() + [260, 320, 400, 500, 600]
    candles = make_series(closes)
    result = run_backtest(candles, timeframe="1m", risk_reward=2.0)
    trade = result.trades[0]
    if trade.outcome == "win":
        assert trade.r_multiple == 2.0

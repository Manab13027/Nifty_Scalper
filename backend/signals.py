from backend.models import Candle, Signal
from backend.indicators import ema, session_vwap, atr, swing_low, swing_high

ATR_PERIOD = 14
SWING_LOOKBACK = 10
# Minimum acceptable distance between entry and stop-loss. Below this, the
# stop-loss is effectively equal to entry (e.g. ATR == 0 on flat candles),
# which would produce a zero-risk-distance signal. One paisa/index-point —
# small enough to never reject a real signal, large enough to absorb float
# precision noise.
MIN_SL_DISTANCE = 0.01


class SignalEngine:
    """Generates BUY/SELL trade signals from an EMA crossover strategy.

    Combines a fast/slow EMA crossover, a session-VWAP directional filter,
    and a no-repeat guard (won't re-fire in the same direction until the
    crossover reverses) with a configurable stop-loss method ("atr" or
    "swing") and a fixed risk-reward multiple for the target.
    """

    def __init__(
        self,
        timeframe: str,
        sl_method: str = "atr",
        fast_ema_period: int = 9,
        slow_ema_period: int = 21,
        atr_multiplier: float = 1.5,
        risk_reward: float = 3.0,
    ):
        if sl_method not in ("atr", "swing"):
            raise ValueError(f"Unsupported sl_method: {sl_method}")
        self.timeframe = timeframe
        self.sl_method = sl_method
        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period
        self.atr_multiplier = atr_multiplier
        self.risk_reward = risk_reward
        self._last_cross_direction: str | None = None

    def evaluate(self, index_candles: list[Candle], futures_price: float) -> Signal | None:
        """Evaluate the latest candle for a new trade signal.

        Must be called once per newly-closed candle, in chronological order,
        passing the full accumulated candle history each time (not per-tick,
        and not with only the latest candle). Indicators such as EMA, VWAP,
        and ATR are recomputed over the whole series on every call and rely
        on that full, in-order history to be correct.

        Returns `None` if there is no actionable signal on this bar. `None`
        is intentionally ambiguous — it can mean: insufficient EMA history,
        no crossover on this bar, a crossover that was filtered out by the
        VWAP condition or the no-repeat guard, or a crossover whose stop-loss
        /target could not be computed (e.g. missing swing data or a
        negligible stop-loss distance). Callers should not try to distinguish
        between these cases; treat `None` uniformly as "no signal this bar."
        """
        closes = [c.close for c in index_candles]
        fast = ema(closes, self.fast_ema_period)
        slow = ema(closes, self.slow_ema_period)
        vwap = session_vwap(index_candles)
        atr_values = atr(index_candles, ATR_PERIOD)

        if len(fast) < 2 or fast[-1] is None or slow[-1] is None or fast[-2] is None or slow[-2] is None:
            return None

        prev_fast, prev_slow = fast[-2], slow[-2]
        curr_fast, curr_slow = fast[-1], slow[-1]
        close = closes[-1]
        curr_vwap = vwap[-1]

        crossed_above = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_below = prev_fast >= prev_slow and curr_fast < curr_slow

        direction: str | None = None
        if crossed_above and close > curr_vwap and self._last_cross_direction != "above":
            direction = "BUY"
            self._last_cross_direction = "above"
        elif crossed_below and close < curr_vwap and self._last_cross_direction != "below":
            direction = "SELL"
            self._last_cross_direction = "below"
        else:
            return None

        stop_loss = self._stop_loss(index_candles, close, direction, atr_values[-1])
        if stop_loss is None:
            return None

        sl_distance = abs(close - stop_loss)
        if sl_distance < MIN_SL_DISTANCE:
            return None

        target = close + sl_distance * self.risk_reward if direction == "BUY" else close - sl_distance * self.risk_reward

        return Signal(
            timestamp=index_candles[-1].timestamp,
            timeframe=self.timeframe,
            direction=direction,
            entry_index_price=close,
            entry_futures_price=futures_price,
            stop_loss=stop_loss,
            target=target,
            rr=self.risk_reward,
            sl_method=self.sl_method,
        )

    def _stop_loss(self, candles: list[Candle], entry: float, direction: str, atr_value: float | None) -> float | None:
        if self.sl_method == "atr":
            if atr_value is None:
                return None
            return entry - atr_value * self.atr_multiplier if direction == "BUY" else entry + atr_value * self.atr_multiplier
        if direction == "BUY":
            low = swing_low(candles, SWING_LOOKBACK)
            return low
        high = swing_high(candles, SWING_LOOKBACK)
        return high

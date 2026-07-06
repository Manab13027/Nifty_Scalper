from backend.models import Candle, Signal
from backend.indicators import ema, session_vwap, atr, swing_low, swing_high

FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5
SWING_LOOKBACK = 10
RISK_REWARD = 3.0


class SignalEngine:
    def __init__(self, timeframe: str, sl_method: str = "atr"):
        if sl_method not in ("atr", "swing"):
            raise ValueError(f"Unsupported sl_method: {sl_method}")
        self.timeframe = timeframe
        self.sl_method = sl_method
        self._last_cross_direction: str | None = None

    def evaluate(self, index_candles: list[Candle], futures_price: float) -> Signal | None:
        closes = [c.close for c in index_candles]
        fast = ema(closes, FAST_EMA_PERIOD)
        slow = ema(closes, SLOW_EMA_PERIOD)
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
        target = close + sl_distance * RISK_REWARD if direction == "BUY" else close - sl_distance * RISK_REWARD

        return Signal(
            timestamp=index_candles[-1].timestamp,
            timeframe=self.timeframe,
            direction=direction,
            entry_index_price=close,
            entry_futures_price=futures_price,
            stop_loss=stop_loss,
            target=target,
            rr=RISK_REWARD,
            sl_method=self.sl_method,
        )

    def _stop_loss(self, candles: list[Candle], entry: float, direction: str, atr_value: float | None) -> float | None:
        if self.sl_method == "atr":
            if atr_value is None:
                return None
            return entry - atr_value * ATR_MULTIPLIER if direction == "BUY" else entry + atr_value * ATR_MULTIPLIER
        low = swing_low(candles, SWING_LOOKBACK)
        high = swing_high(candles, SWING_LOOKBACK)
        if low is None or high is None:
            return None
        return low if direction == "BUY" else high

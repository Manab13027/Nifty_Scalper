from datetime import date
from backend.models import Candle


def ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    result: list[float | None] = [None] * (period - 1)
    seed = sum(values[:period]) / period
    result.append(seed)
    prev = seed
    for price in values[period:]:
        current = (price - prev) * multiplier + prev
        result.append(current)
        prev = current
    return result


def session_vwap(candles: list[Candle]) -> list[float]:
    result: list[float] = []
    cum_pv = 0.0
    cum_vol = 0.0
    current_day: date | None = None
    for c in candles:
        day = c.timestamp.date()
        if day != current_day:
            current_day = day
            cum_pv = 0.0
            cum_vol = 0.0
        typical = (c.high + c.low + c.close) / 3
        cum_pv += typical * c.volume
        cum_vol += c.volume
        result.append(cum_pv / cum_vol if cum_vol else typical)
    return result


def atr(candles: list[Candle], period: int = 14) -> list[float | None]:
    if len(candles) < period + 1:
        return [None] * len(candles)
    trs: list[float] = [0.0]
    for i in range(1, len(candles)):
        high, low, prev_close = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    result: list[float | None] = [None] * period
    seed = sum(trs[1:period + 1]) / period
    result.append(seed)
    prev_atr = seed
    for i in range(period + 1, len(candles)):
        prev_atr = (prev_atr * (period - 1) + trs[i]) / period
        result.append(prev_atr)
    return result


def swing_low(candles: list[Candle], lookback: int = 10) -> float | None:
    if len(candles) < lookback:
        return None
    return min(c.low for c in candles[-lookback:])


def swing_high(candles: list[Candle], lookback: int = 10) -> float | None:
    if len(candles) < lookback:
        return None
    return max(c.high for c in candles[-lookback:])

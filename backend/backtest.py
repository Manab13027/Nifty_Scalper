from dataclasses import dataclass, field
from datetime import datetime

from backend.models import Candle
from backend.signals import SignalEngine


@dataclass
class SimulatedTrade:
    direction: str
    entry_time: datetime
    entry_price: float
    signal_stop_loss: float
    signal_target: float
    outcome: str  # "win" | "loss" | "open"
    r_multiple: float | None
    exit_time: datetime | None
    exit_price: float | None


@dataclass
class BacktestResult:
    trades: list[SimulatedTrade] = field(default_factory=list)
    total_signals: int = 0

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.outcome == "win")

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.outcome == "loss")

    @property
    def win_rate(self) -> float | None:
        closed = self.wins + self.losses
        return self.wins / closed if closed else None

    @property
    def total_r(self) -> float:
        return sum(t.r_multiple for t in self.trades if t.r_multiple is not None)


def _resolve_exit(direction: str, candle: Candle, stop_loss: float, target: float) -> tuple[str, float] | None:
    """Return (outcome, exit_price) if this candle closes the trade, else None.

    A candle touching both SL and target counts as a loss (conservative — we
    can't know intra-candle ordering from OHLC data alone).
    """
    if direction == "BUY":
        hit_sl = candle.low <= stop_loss
        hit_target = candle.high >= target
    else:
        hit_sl = candle.high >= stop_loss
        hit_target = candle.low <= target
    if hit_sl:
        return ("loss", stop_loss)
    if hit_target:
        return ("win", target)
    return None


def run_backtest(
    candles: list[Candle],
    timeframe: str,
    sl_method: str = "atr",
    fast_ema_period: int = 9,
    slow_ema_period: int = 21,
    atr_multiplier: float = 1.5,
    risk_reward: float = 3.0,
) -> BacktestResult:
    """Replay closed candles through a fresh SignalEngine and simulate trades.

    One position at a time: while a trade is open, further signals are counted
    but not taken. Entry is at the signal candle's close; SL/target checks
    begin on the next candle. Wins/losses are measured in R-multiples
    (win = +risk_reward, loss = -1; exits exactly at SL/target, no slippage).
    Trades unresolved when data ends are reported with outcome "open".
    """
    engine = SignalEngine(
        timeframe,
        sl_method=sl_method,
        fast_ema_period=fast_ema_period,
        slow_ema_period=slow_ema_period,
        atr_multiplier=atr_multiplier,
        risk_reward=risk_reward,
    )
    result = BacktestResult()
    open_trade: SimulatedTrade | None = None

    for i in range(1, len(candles) + 1):
        window = candles[:i]
        current = window[-1]

        # Exit check first: the entry candle itself is never checked because
        # open_trade is only set after this block runs for that candle.
        if open_trade is not None:
            exit_info = _resolve_exit(
                open_trade.direction, current, open_trade.signal_stop_loss, open_trade.signal_target,
            )
            if exit_info:
                outcome, exit_price = exit_info
                open_trade.outcome = outcome
                open_trade.exit_price = exit_price
                open_trade.exit_time = current.timestamp
                open_trade.r_multiple = risk_reward if outcome == "win" else -1.0
                open_trade = None

        signal = engine.evaluate(window, futures_price=current.close)
        if signal is None:
            continue
        result.total_signals += 1
        if open_trade is not None:
            continue  # position already open — signal counted but not taken
        open_trade = SimulatedTrade(
            direction=signal.direction,
            entry_time=signal.timestamp,
            entry_price=signal.entry_index_price,
            signal_stop_loss=signal.stop_loss,
            signal_target=signal.target,
            outcome="open",
            r_multiple=None,
            exit_time=None,
            exit_price=None,
        )
        result.trades.append(open_trade)

    return result

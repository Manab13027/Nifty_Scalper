from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    timestamp: datetime
    timeframe: str
    direction: Literal["BUY", "SELL"]
    entry_index_price: float
    entry_futures_price: float
    stop_loss: float
    target: float
    rr: float
    sl_method: Literal["atr", "swing"]

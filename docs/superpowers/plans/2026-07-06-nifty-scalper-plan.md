# Nifty Scalper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python/FastAPI service that streams live Nifty 50 index data from Dhan, computes EMA/VWAP scalping signals with ATR- or swing-based stop loss and fixed 1:3 risk-reward, and renders them as annotated arrows on a live multi-timeframe web dashboard.

**Architecture:** A FastAPI backend aggregates Dhan tick data into 1m/15m/1h/day candles (`CandleBuilder`), runs an independent `SignalEngine` per timeframe on every closed candle, logs fired signals to SQLite, and pushes candle/signal updates over a WebSocket to a static browser dashboard (lightweight-charts) that draws buy/sell arrows with SL/target and beeps on new signals.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, dhanhq SDK, SQLite (stdlib `sqlite3`), pytest, vanilla JS + lightweight-charts (CDN) for the frontend.

---

## File Structure

```
Nifty_Scalper/
├── requirements.txt
├── .env.example
├── .gitignore
├── backend/
│   ├── __init__.py
│   ├── config.py        # env-based settings
│   ├── models.py        # Candle, Signal dataclasses
│   ├── indicators.py    # ema, session_vwap, atr, swing_low, swing_high
│   ├── candles.py        # CandleBuilder (tick aggregation) + resample()
│   ├── signals.py        # SignalEngine (crossover + SL/target)
│   ├── storage.py        # SQLite signal log
│   ├── dhan_client.py    # thin wrapper around dhanhq SDK
│   └── main.py            # FastAPI app, WebSocket, live feed wiring
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── tests/
    ├── test_config.py
    ├── test_indicators.py
    ├── test_candles.py
    ├── test_signals.py
    ├── test_storage.py
    └── test_dhan_client.py
```

---

### Task 1: Project scaffolding + config

**Files:**
- Create: `requirements.txt`, `.env.example`, `.gitignore`, `backend/__init__.py`, `backend/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Init git and create scaffolding files**

```bash
cd /Users/fighter/Documents/Projects_Folder/Nifty_Scalper
git init
mkdir -p backend tests frontend
touch backend/__init__.py
```

`requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
python-dotenv==1.0.1
dhanhq==2.0.2
pytest==8.3.3
httpx==0.27.2
```

`.env.example`:
```
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token
SL_METHOD=atr
DB_PATH=signals.db
```

`.gitignore`:
```
.env
*.db
__pycache__/
*.pyc
.venv/
```

- [ ] **Step 2: Write the failing test for config loading**

`tests/test_config.py`:
```python
from backend.config import load_settings


def test_load_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "abc123")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "tok456")
    monkeypatch.setenv("SL_METHOD", "swing")
    monkeypatch.setenv("DB_PATH", "test.db")
    settings = load_settings()
    assert settings.dhan_client_id == "abc123"
    assert settings.dhan_access_token == "tok456"
    assert settings.sl_method == "swing"
    assert settings.db_path == "test.db"


def test_load_settings_defaults(monkeypatch):
    monkeypatch.delenv("SL_METHOD", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    settings = load_settings()
    assert settings.sl_method == "atr"
    assert settings.db_path == "signals.db"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.config'`

- [ ] **Step 4: Write minimal implementation**

`backend/config.py`:
```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    dhan_client_id: str
    dhan_access_token: str
    sl_method: str
    db_path: str


def load_settings() -> Settings:
    return Settings(
        dhan_client_id=os.environ.get("DHAN_CLIENT_ID", ""),
        dhan_access_token=os.environ.get("DHAN_ACCESS_TOKEN", ""),
        sl_method=os.environ.get("SL_METHOD", "atr"),
        db_path=os.environ.get("DB_PATH", "signals.db"),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore backend/__init__.py backend/config.py tests/test_config.py
git commit -m "feat: project scaffolding and env-based config"
```

---

### Task 2: Data models

**Files:**
- Create: `backend/models.py`

- [ ] **Step 1: Write the models (no test needed — plain dataclasses)**

`backend/models.py`:
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/models.py
git commit -m "feat: add Candle and Signal data models"
```

---

### Task 3: Indicators (EMA, VWAP, ATR, swing high/low)

**Files:**
- Create: `backend/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_indicators.py`:
```python
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


def test_atr_returns_none_until_period_plus_one_candles():
    candles = [make_candle(datetime(2026, 7, 1) + timedelta(minutes=i), 100, 105, 95, 100) for i in range(10)]
    result = atr(candles, period=14)
    assert result == [None] * 10


def test_atr_computes_seed_after_enough_candles():
    candles = [make_candle(datetime(2026, 7, 1) + timedelta(minutes=i), 100, 105, 95, 100) for i in range(16)]
    result = atr(candles, period=14)
    assert result[14] is not None
    assert result[14] == 10.0


def test_swing_low_and_high_use_lookback_window():
    candles = [make_candle(datetime(2026, 7, 1) + timedelta(minutes=i), 100, 100 + i, 100 - i, 100) for i in range(12)]
    assert swing_low(candles, lookback=10) == 100 - 11
    assert swing_high(candles, lookback=10) == 100 + 11


def test_swing_low_returns_none_if_not_enough_candles():
    candles = [make_candle(datetime(2026, 7, 1), 100, 105, 95, 100)]
    assert swing_low(candles, lookback=10) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indicators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.indicators'`

- [ ] **Step 3: Write minimal implementation**

`backend/indicators.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indicators.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/indicators.py tests/test_indicators.py
git commit -m "feat: add EMA, session VWAP, ATR, and swing high/low indicators"
```

---

### Task 4: CandleBuilder + resample

**Files:**
- Create: `backend/candles.py`
- Test: `tests/test_candles.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_candles.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_candles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.candles'`

- [ ] **Step 3: Write minimal implementation**

`backend/candles.py`:
```python
from datetime import datetime, timedelta
from backend.models import Candle

TIMEFRAME_SECONDS = {
    "1m": 60,
    "15m": 900,
    "1h": 3600,
    "day": 86400,
}


class CandleBuilder:
    def __init__(self, timeframe: str):
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        self.timeframe = timeframe
        self._bucket_seconds = TIMEFRAME_SECONDS[timeframe]
        self.candles: list[Candle] = []
        self._current_bucket_start: datetime | None = None

    def _bucket_start(self, ts: datetime) -> datetime:
        midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.timeframe == "day":
            return midnight
        seconds_since_midnight = (ts - midnight).total_seconds()
        offset = seconds_since_midnight - (seconds_since_midnight % self._bucket_seconds)
        return midnight + timedelta(seconds=offset)

    def add_tick(self, timestamp: datetime, price: float, volume: float = 0.0) -> Candle | None:
        bucket_start = self._bucket_start(timestamp)
        closed: Candle | None = None
        if self._current_bucket_start is None:
            self._current_bucket_start = bucket_start
            self.candles.append(Candle(bucket_start, price, price, price, price, volume))
        elif bucket_start != self._current_bucket_start:
            closed = self.candles[-1]
            self._current_bucket_start = bucket_start
            self.candles.append(Candle(bucket_start, price, price, price, price, volume))
        else:
            live = self.candles[-1]
            live.high = max(live.high, price)
            live.low = min(live.low, price)
            live.close = price
            live.volume += volume
        return closed

    def seed(self, candles: list[Candle]) -> None:
        self.candles = list(candles)
        if self.candles:
            self._current_bucket_start = self._bucket_start(self.candles[-1].timestamp)


def resample(candles: list[Candle], timeframe: str) -> list[Candle]:
    """Resample 1-minute OHLCV candles into a coarser timeframe."""
    builder = CandleBuilder(timeframe)
    result: list[Candle] = []
    for c in candles:
        bucket_start = builder._bucket_start(c.timestamp)
        if builder._current_bucket_start is None or bucket_start != builder._current_bucket_start:
            if builder.candles:
                result.append(builder.candles[-1])
            builder._current_bucket_start = bucket_start
            builder.candles.append(Candle(bucket_start, c.open, c.high, c.low, c.close, c.volume))
        else:
            live = builder.candles[-1]
            live.high = max(live.high, c.high)
            live.low = min(live.low, c.low)
            live.close = c.close
            live.volume += c.volume
    if builder.candles:
        result.append(builder.candles[-1])
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_candles.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/candles.py tests/test_candles.py
git commit -m "feat: add CandleBuilder tick aggregation and resample helper"
```

---

### Task 5: SignalEngine

**Files:**
- Create: `backend/signals.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_signals.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_signals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.signals'`

- [ ] **Step 3: Write minimal implementation**

`backend/signals.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_signals.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/signals.py tests/test_signals.py
git commit -m "feat: add SignalEngine with EMA/VWAP crossover and SL/target calc"
```

---

### Task 6: SQLite signal storage

**Files:**
- Create: `backend/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_storage.py`:
```python
from datetime import datetime
from backend.models import Signal
from backend.storage import init_db, insert_signal, get_recent_signals


def make_signal(direction="BUY"):
    return Signal(
        timestamp=datetime(2026, 7, 1, 9, 20),
        timeframe="1m",
        direction=direction,
        entry_index_price=100.0,
        entry_futures_price=101.0,
        stop_loss=95.0,
        target=115.0,
        rr=3.0,
        sl_method="atr",
    )


def test_insert_and_fetch_signal(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    insert_signal(conn, make_signal())
    rows = get_recent_signals(conn)
    assert len(rows) == 1
    assert rows[0]["direction"] == "BUY"
    assert rows[0]["stop_loss"] == 95.0


def test_get_recent_signals_respects_limit_and_order(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    insert_signal(conn, make_signal("BUY"))
    insert_signal(conn, make_signal("SELL"))
    rows = get_recent_signals(conn, limit=1)
    assert len(rows) == 1
    assert rows[0]["direction"] == "SELL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.storage'`

- [ ] **Step 3: Write minimal implementation**

`backend/storage.py`:
```python
import sqlite3
from backend.models import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_index_price REAL NOT NULL,
    entry_futures_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target REAL NOT NULL,
    rr REAL NOT NULL,
    sl_method TEXT NOT NULL
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def insert_signal(conn: sqlite3.Connection, signal: Signal) -> None:
    conn.execute(
        """INSERT INTO signals
           (timestamp, timeframe, direction, entry_index_price, entry_futures_price,
            stop_loss, target, rr, sl_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal.timestamp.isoformat(),
            signal.timeframe,
            signal.direction,
            signal.entry_index_price,
            signal.entry_futures_price,
            signal.stop_loss,
            signal.target,
            signal.rr,
            signal.sl_method,
        ),
    )
    conn.commit()


def get_recent_signals(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    cursor = conn.execute(
        "SELECT timestamp, timeframe, direction, entry_index_price, entry_futures_price, "
        "stop_loss, target, rr, sl_method FROM signals ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/storage.py tests/test_storage.py
git commit -m "feat: add SQLite signal history storage"
```

---

### Task 7: Dhan client wrapper

**Files:**
- Create: `backend/dhan_client.py`
- Test: `tests/test_dhan_client.py`

**Note:** Verify method names/response shape against current Dhan API docs (https://dhanhq.co/docs/) before running live — the `dhanhq` SDK interface may have changed since this plan was written. `NIFTY_INDEX_SECURITY_ID = "13"` and exchange segment `IDX_I` are Dhan's documented identifiers for the Nifty 50 index as of this writing; confirm via Dhan's instrument master CSV if signals look wrong. Nifty futures security_id changes every expiry and must be looked up from Dhan's instrument master at runtime — this task wraps the historical index fetch only; futures price lookup is wired in Task 9.

- [ ] **Step 1: Write the failing test using a mocked SDK**

`tests/test_dhan_client.py`:
```python
from unittest.mock import MagicMock
from backend.dhan_client import DhanClient


def test_fetch_intraday_candles_parses_response(monkeypatch):
    fake_response = {
        "data": {
            "timestamp": [1751350500, 1751350560],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1200],
        }
    }
    mock_sdk = MagicMock()
    mock_sdk.intraday_minute_data.return_value = fake_response
    monkeypatch.setattr("backend.dhan_client.dhanhq", lambda *a, **k: mock_sdk)

    client = DhanClient("client_id", "access_token")
    candles = client.fetch_intraday_candles("13", "IDX_I", "INDEX", "2026-07-01", "2026-07-01")

    assert len(candles) == 2
    assert candles[0].open == 100.0
    assert candles[1].close == 102.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dhan_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.dhan_client'`

- [ ] **Step 3: Write minimal implementation**

`backend/dhan_client.py`:
```python
from datetime import datetime
from dhanhq import dhanhq
from backend.models import Candle

NIFTY_INDEX_SECURITY_ID = "13"
NIFTY_INDEX_EXCHANGE_SEGMENT = "IDX_I"


class DhanClient:
    def __init__(self, client_id: str, access_token: str):
        self._dhan = dhanhq(client_id, access_token)

    def fetch_intraday_candles(
        self, security_id: str, exchange_segment: str, instrument_type: str,
        from_date: str, to_date: str,
    ) -> list[Candle]:
        response = self._dhan.intraday_minute_data(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            from_date=from_date,
            to_date=to_date,
        )
        data = response.get("data", response)
        candles = []
        for i in range(len(data["open"])):
            candles.append(Candle(
                timestamp=datetime.fromtimestamp(data["timestamp"][i]),
                open=data["open"][i],
                high=data["high"][i],
                low=data["low"][i],
                close=data["close"][i],
                volume=data["volume"][i],
            ))
        return candles
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dhan_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/dhan_client.py tests/test_dhan_client.py
git commit -m "feat: add Dhan API client wrapper for historical candles"
```

---

### Task 8: FastAPI backend + WebSocket server

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Write the backend entrypoint**

`backend/main.py`:
```python
import asyncio
import json
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.config import load_settings
from backend.candles import CandleBuilder, resample
from backend.signals import SignalEngine
from backend.storage import init_db, insert_signal
from backend.dhan_client import DhanClient, NIFTY_INDEX_SECURITY_ID, NIFTY_INDEX_EXCHANGE_SEGMENT

TIMEFRAMES = ["1m", "15m", "1h", "day"]

app = FastAPI()
settings = load_settings()
db_conn = init_db(settings.db_path)

builders: dict[str, CandleBuilder] = {tf: CandleBuilder(tf) for tf in TIMEFRAMES}
engines: dict[str, SignalEngine] = {tf: SignalEngine(tf, settings.sl_method) for tf in TIMEFRAMES}
connected_clients: list[WebSocket] = []


@app.on_event("startup")
async def backfill() -> None:
    client = DhanClient(settings.dhan_client_id, settings.dhan_access_token)
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    one_min = client.fetch_intraday_candles(
        NIFTY_INDEX_SECURITY_ID, NIFTY_INDEX_EXCHANGE_SEGMENT, "INDEX", from_date, to_date,
    )
    builders["1m"].seed(one_min)
    for tf in ("15m", "1h", "day"):
        builders[tf].seed(resample(one_min, tf))


def _candle_to_json(c) -> dict:
    return {
        "timestamp": c.timestamp.isoformat(),
        "open": c.open, "high": c.high, "low": c.low, "close": c.close,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        for tf in TIMEFRAMES:
            await websocket.send_text(json.dumps({
                "type": "history",
                "timeframe": tf,
                "candles": [_candle_to_json(c) for c in builders[tf].candles],
            }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)


async def broadcast(message: dict) -> None:
    dead = []
    for client in connected_clients:
        try:
            await client.send_text(json.dumps(message))
        except Exception:
            dead.append(client)
    for client in dead:
        connected_clients.remove(client)


def on_index_tick(timestamp: datetime, price: float, futures_price: float, volume: float = 0.0) -> None:
    """Feed one Nifty 50 index tick into every timeframe's candle builder and signal engine."""
    for tf in TIMEFRAMES:
        closed = builders[tf].add_tick(timestamp, price, volume)
        if closed:
            signal = engines[tf].evaluate(builders[tf].candles, futures_price)
            if signal:
                insert_signal(db_conn, signal)
                asyncio.create_task(broadcast({
                    "type": "signal",
                    "timeframe": tf,
                    "direction": signal.direction,
                    "timestamp": signal.timestamp.isoformat(),
                    "entry_index_price": signal.entry_index_price,
                    "entry_futures_price": signal.entry_futures_price,
                    "stop_loss": signal.stop_loss,
                    "target": signal.target,
                    "rr": signal.rr,
                }))


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

- [ ] **Step 2: Verify the server boots**

Run: `cd /Users/fighter/Documents/Projects_Folder/Nifty_Scalper && cp .env.example .env` (fill in real Dhan credentials), then:
Run: `uvicorn backend.main:app --reload --port 8000`
Expected: server starts without exceptions; `GET http://localhost:8000/` returns the (not-yet-created) frontend page (404 until Task 9 adds `frontend/index.html` — that's expected at this point).

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add FastAPI backend with WebSocket candle/signal streaming"
```

---

### Task 9: Frontend dashboard

**Files:**
- Create: `frontend/index.html`, `frontend/style.css`, `frontend/app.js`

- [ ] **Step 1: Write the dashboard shell**

`frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Nifty Scalper</title>
  <link rel="stylesheet" href="style.css" />
  <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>
  <div id="tabs">
    <button class="tab-btn active" data-tf="1m">1m</button>
    <button class="tab-btn" data-tf="15m">15m</button>
    <button class="tab-btn" data-tf="1h">1h</button>
    <button class="tab-btn" data-tf="day">Day</button>
  </div>
  <div id="chart"></div>
  <aside id="signal-panel">
    <h2>Recent Signals</h2>
    <ul id="signal-list"></ul>
  </aside>
  <script src="app.js"></script>
</body>
</html>
```

`frontend/style.css`:
```css
body {
  margin: 0;
  font-family: sans-serif;
  display: flex;
  height: 100vh;
}
#tabs {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 10;
}
.tab-btn {
  padding: 6px 12px;
  margin-right: 4px;
  cursor: pointer;
}
.tab-btn.active {
  background: #333;
  color: white;
}
#chart {
  flex: 1;
}
#signal-panel {
  width: 280px;
  overflow-y: auto;
  border-left: 1px solid #ddd;
  padding: 10px;
}
#signal-list li {
  margin-bottom: 8px;
  font-size: 13px;
  border-bottom: 1px solid #eee;
  padding-bottom: 6px;
}
.buy { color: #16a34a; }
.sell { color: #dc2626; }
```

`frontend/app.js`:
```javascript
const chartEl = document.getElementById("chart");
const chart = LightweightCharts.createChart(chartEl, {
  height: window.innerHeight,
  layout: { background: { color: "#fff" }, textColor: "#000" },
});
const candleSeries = chart.addCandlestickSeries();

const state = {
  activeTimeframe: "1m",
  candlesByTimeframe: {},
  markersByTimeframe: {},
};

function toSeriesData(candles) {
  return candles.map((c) => ({
    time: Math.floor(new Date(c.timestamp).getTime() / 1000),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

function renderActiveTimeframe() {
  const candles = state.candlesByTimeframe[state.activeTimeframe] || [];
  candleSeries.setData(toSeriesData(candles));
  candleSeries.setMarkers(state.markersByTimeframe[state.activeTimeframe] || []);
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.activeTimeframe = btn.dataset.tf;
    renderActiveTimeframe();
  });
});

function beep() {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const osc = ctx.createOscillator();
  osc.frequency.value = 880;
  osc.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + 0.15);
}

function addSignalToPanel(signal) {
  const list = document.getElementById("signal-list");
  const item = document.createElement("li");
  item.className = signal.direction === "BUY" ? "buy" : "sell";
  item.textContent = `[${signal.timeframe}] ${signal.direction} @ ${signal.entry_futures_price.toFixed(2)} | SL ${signal.stop_loss.toFixed(2)} | Target ${signal.target.toFixed(2)} | RR 1:${signal.rr}`;
  list.prepend(item);
}

const ws = new WebSocket(`ws://${window.location.host}/ws`);

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "history") {
    state.candlesByTimeframe[message.timeframe] = message.candles;
    state.markersByTimeframe[message.timeframe] = [];
    if (message.timeframe === state.activeTimeframe) renderActiveTimeframe();
  } else if (message.type === "signal") {
    const marker = {
      time: Math.floor(new Date(message.timestamp).getTime() / 1000),
      position: message.direction === "BUY" ? "belowBar" : "aboveBar",
      color: message.direction === "BUY" ? "#16a34a" : "#dc2626",
      shape: message.direction === "BUY" ? "arrowUp" : "arrowDown",
      text: `SL ${message.stop_loss.toFixed(0)} / TG ${message.target.toFixed(0)}`,
    };
    const markers = state.markersByTimeframe[message.timeframe] || [];
    markers.push(marker);
    state.markersByTimeframe[message.timeframe] = markers;
    if (message.timeframe === state.activeTimeframe) renderActiveTimeframe();
    addSignalToPanel(message);
    beep();
  }
};
```

- [ ] **Step 2: Verify in browser**

Run: `uvicorn backend.main:app --reload --port 8000`, open `http://localhost:8000/` in a browser.
Expected: dashboard loads, tabs switch, chart renders (empty until live/backfilled data arrives), no console errors on WebSocket connect.

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add live dashboard with multi-timeframe charts and signal markers"
```

---

### Task 10: Wire Dhan live feed into the backend

**Files:**
- Modify: `backend/main.py`

**Note:** Verify the `dhanhq.marketfeed` API (subscription tuple format, event loop integration) against current Dhan docs before running live — this is the part of the SDK most likely to have changed. Nifty futures security_id must be looked up from Dhan's published instrument/scrip master for the current expiry; hardcode it via `.env` (`NIFTY_FUT_SECURITY_ID`) and refresh manually each expiry rather than auto-resolving, to keep this task scoped.

- [ ] **Step 1: Add `nifty_fut_security_id` to config**

Add to the `Settings` dataclass in `backend/config.py`:
```python
    nifty_fut_security_id: str
```
Add to `load_settings()`'s return statement in the same file:
```python
        nifty_fut_security_id=os.environ.get("NIFTY_FUT_SECURITY_ID", ""),
```
Add to `.env.example`:
```
NIFTY_FUT_SECURITY_ID=your_current_month_nifty_fut_security_id
```

- [ ] **Step 2: Add the live feed task with reconnect backoff**

Add to `backend/main.py` (top-level import and new functions, after `backfill`):
```python
from dhanhq import marketfeed

_latest_futures_price = {"value": 0.0}
_last_tick_at = {"value": None}

RECONNECT_BACKOFF_SECONDS = [1, 2, 5, 10, 30]


async def run_live_feed() -> None:
    """Consume Dhan's live tick feed and reconnect with backoff on disconnect.
    Runs for the lifetime of the app; the market-closed case is a normal
    disconnect/no-data state handled by the same backoff loop."""
    instruments = [
        (marketfeed.NSE, NIFTY_INDEX_SECURITY_ID, marketfeed.Ticker),
        (marketfeed.NSE_FNO, settings.nifty_fut_security_id, marketfeed.Ticker),
    ]
    attempt = 0
    while True:
        try:
            feed = marketfeed.DhanFeed(
                settings.dhan_client_id, settings.dhan_access_token, instruments, version="v2",
            )
            await asyncio.to_thread(feed.run_forever)
            data = feed.get_data()
            attempt = 0
            if data is None:
                continue
            _last_tick_at["value"] = datetime.now()
            if data.get("security_id") == settings.nifty_fut_security_id:
                _latest_futures_price["value"] = data["LTP"]
            elif data.get("security_id") == NIFTY_INDEX_SECURITY_ID:
                on_index_tick(
                    datetime.now(), data["LTP"], _latest_futures_price["value"] or data["LTP"],
                )
        except Exception:
            delay = RECONNECT_BACKOFF_SECONDS[min(attempt, len(RECONNECT_BACKOFF_SECONDS) - 1)]
            attempt += 1
            await asyncio.sleep(delay)


@app.on_event("startup")
async def start_live_feed() -> None:
    asyncio.create_task(run_live_feed())
```

- [ ] **Step 3: Surface staleness on the dashboard**

Add a `/status` endpoint to `backend/main.py` so the frontend can show when data last arrived:
```python
@app.get("/status")
async def status() -> dict:
    last = _last_tick_at["value"]
    return {"last_tick_at": last.isoformat() if last else None}
```

Add to `frontend/index.html`, inside `<div id="tabs">` after the last button:
```html
    <span id="status-indicator">no data yet</span>
```
Add to `frontend/app.js` (bottom of file):
```javascript
async function pollStatus() {
  const res = await fetch("/status");
  const { last_tick_at } = await res.json();
  const el = document.getElementById("status-indicator");
  if (!last_tick_at) {
    el.textContent = "no data yet";
    return;
  }
  const secondsAgo = (Date.now() - new Date(last_tick_at).getTime()) / 1000;
  el.textContent = secondsAgo > 60 ? `stale (${Math.floor(secondsAgo)}s ago)` : "live";
}
setInterval(pollStatus, 5000);
pollStatus();
```

- [ ] **Step 4: Manual verification against live market**

Run: `uvicorn backend.main:app --reload --port 8000` during NSE market hours (9:15–15:30 IST) with real Dhan credentials and the current month's Nifty futures `security_id` in `.env`.
Expected: dashboard candles update live, status indicator shows "live"; when an EMA/VWAP crossover occurs, an arrow appears with SL/target and a beep plays. Outside market hours, status indicator shows "stale" after 60s of no ticks.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/config.py .env.example frontend/index.html frontend/app.js
git commit -m "feat: wire live Dhan feed into candle builders with reconnect backoff and staleness indicator"
```

---

### Task 11: End-to-end verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: all tests from Tasks 1–7 pass (config, indicators, candles, signals, storage, dhan_client).

- [ ] **Step 2: Manual smoke test checklist**

- [ ] Server boots with `uvicorn backend.main:app --reload --port 8000` without exceptions
- [ ] Dashboard loads at `http://localhost:8000/`, all 4 tabs switch correctly
- [ ] Backfilled candles appear on each timeframe on load
- [ ] During market hours, live candles update without page refresh
- [ ] A signal (real or manually triggered via a temporary test tick) shows an arrow with SL/target text and triggers a beep
- [ ] Signal appears in the sidebar list with correct direction/SL/target/RR
- [ ] Restarting the server preserves prior signals in `signals.db` (query via `sqlite3 signals.db "select * from signals;"`)

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify end-to-end signal flow"
```

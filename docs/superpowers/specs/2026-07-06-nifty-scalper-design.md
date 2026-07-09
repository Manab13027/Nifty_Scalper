# Nifty Scalper — Signal & Annotation Tool

## Purpose

A local tool that watches Nifty 50 index price action across multiple timeframes,
detects scalping entries via an EMA/VWAP strategy, and annotates a live chart
dashboard with buy/sell arrows, stop loss, and risk-to-reward. No order
execution — the trader decides whether to act on each signal.

## Scope

- Signal/annotation only. No real or paper order placement, no broker execution.
- Live data sourced from Dhan API (WebSocket ticks + historical REST for
  backfill/seeding).
- Instrument: signals generated off **Nifty 50 index** price; **Nifty futures
  (current month)** price captured alongside each signal as the actual
  tradeable reference (since futures ≠ spot).
- Timeframes: 1m, 15m, 1h, Day — each with an independent signal engine.

## Architecture

```
Dhan API (WebSocket ticks + historical REST)
        │
        ▼
Python Backend (FastAPI)
  - candle builder (aggregates ticks → 1m/15m/1h/day candles per instrument)
  - signal engine (runs per timeframe on every closed candle)
  - SQLite (signal history log)
  - WebSocket server (pushes live candle/signal updates to browser)
        │
        ▼
Web Dashboard (browser, lightweight-charts)
  - tab per timeframe
  - candlesticks + EMA9/EMA21 + VWAP overlay
  - ▲/▼ markers with SL/target/RR annotation
  - signal history sidebar
  - browser beep (Web Audio API) on new signal
```

## Signal Logic

- **Indicators per timeframe**: EMA(9) fast, EMA(21) slow, session VWAP
  (resets at market open 9:15 IST), ATR(14).
- **Entry trigger**:
  - BUY: fast EMA crosses above slow EMA AND close > VWAP.
  - SELL: fast EMA crosses below slow EMA AND close < VWAP.
- **Stop loss** (configurable, default ATR):
  - ATR method: SL = entry ∓ (ATR × 1.5)
  - Swing method: SL = last swing low/high over a 10-candle lookback
- **Target**: entry ± (SL distance × 3) — fixed 1:3 risk-to-reward.
- Signal fires once per crossover; no repeat signal until EMAs cross back.
- Timeframes are independent — a 1m and 1h signal may disagree; each is
  shown on its own tab.

## Dashboard & Config

- **Layout**: tabs for 1m / 15m / 1h / Day, each a candlestick chart with
  EMA9/EMA21, VWAP, and signal markers.
- **Signal panel**: sidebar listing recent signals across all timeframes
  (timestamp, direction, entry, SL, target); clicking one jumps the chart to
  that candle.
- **Alerts**: new signal → arrow + browser beep. No external notification
  service (no Telegram, no SMS).
- **Config** (`.env`, gitignored): Dhan API key/secret/access token, EMA
  periods, ATR multiplier, SL method toggle (`atr`/`swing`), RR ratio —
  overridable without code changes.
- **Secrets**: Dhan credentials loaded from `.env` only; never hardcoded or
  logged.

## Data Handling / Error Cases

- On startup, backfill each timeframe from Dhan's historical intraday API
  before switching to live WebSocket aggregation.
- Handle market-closed state (no ticks) without crashing — dashboard shows
  last session's data, clearly marked as stale/closed.
- WebSocket reconnect with backoff on Dhan feed disconnects.
- Missing/gapped candle data is skipped rather than fabricated.

## Storage

- SQLite table `signals`: timestamp, timeframe, direction, entry_index,
  entry_futures_price, stop_loss, target, rr, sl_method. Purely a record for
  later review — not used for execution.

## Testing

- Unit tests for EMA, VWAP, ATR, and swing-high/low calculations against
  fixed fixture data.
- Unit tests for signal trigger logic (crossover + VWAP filter) with known
  candle sequences producing expected BUY/SELL/no-signal outcomes.
- Unit tests for SL/target math under both `atr` and `swing` modes.

## Backtesting (added 2026-07-09)

- Dashboard "Backtest" tab: date range + timeframe pickers; runs the same
  strategy (same `.env` parameters) over Dhan historical data via
  `GET /backtest`.
- Trade simulation: entry at signal close; walk forward candle by candle,
  SL or target hit — whichever first; a candle touching both counts as a
  loss (conservative). One position at a time; further signals while open
  are counted but not taken. Trades unresolved at data end reported "open".
- Results in R-multiples (win = +RR, loss = −1; no slippage modeling) with
  win rate, totals, and entry/exit markers plotted on the chart.

## Out of Scope (for this spec)

- Order execution (live or paper).
- Multi-instrument support beyond Nifty index + Nifty futures.
- Alerting beyond on-screen arrows + browser beep (no Telegram/SMS/email).

# Nifty Scalper

An **intraday trading-signal app for Nifty / index options**. A FastAPI backend
connects to the Dhan broker API to read market data, computes short-term
("scalping") signals, stores them in a local database, and serves them to a web
frontend.

## Features
- Dhan broker integration (`dhanhq`) for live data
- Signal generation + persistence (`signals.db`)
- FastAPI backend + web frontend
- Test suite (`pytest`)

## Stack
Python · FastAPI · dhanhq · SQLite

## Getting started
```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload     # see backend/ for the exact entrypoint
```

## Notes
- Requires valid Dhan API credentials.
- **Not financial advice.** Trading involves risk; test on paper first.

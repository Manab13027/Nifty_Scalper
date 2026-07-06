import asyncio
import json
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.config import load_settings
from backend.candles import CandleBuilder, resample
from backend.signals import SignalEngine
from backend.storage import init_db, insert_signal
from backend.dhan_client import DhanClient, NIFTY_INDEX_SECURITY_ID, NIFTY_INDEX_EXCHANGE_SEGMENT

logger = logging.getLogger("nifty_scalper")

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
    try:
        one_min = client.fetch_intraday_candles(
            NIFTY_INDEX_SECURITY_ID, NIFTY_INDEX_EXCHANGE_SEGMENT, "INDEX", from_date, to_date,
        )
    except Exception:
        logger.exception("Historical backfill failed — starting with empty candle history")
        return
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
    """Feed one Nifty 50 index tick into every timeframe's candle builder and signal engine.
    Must be called from the same thread that called init_db()/created the app's sqlite3
    connection — sqlite3 connections are not thread-safe by default (check_same_thread=True)."""
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

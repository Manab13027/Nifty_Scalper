import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.config import load_settings
from backend.candles import CandleBuilder, resample
from backend.signals import SignalEngine
from backend.storage import init_db, insert_signal
from backend.dhan_client import DhanClient, NIFTY_INDEX_SECURITY_ID, NIFTY_INDEX_EXCHANGE_SEGMENT
from dhanhq import marketfeed

logger = logging.getLogger("nifty_scalper")

TIMEFRAMES = ["1m", "15m", "1h", "day"]

settings = load_settings()
db_conn = init_db(settings.db_path)

builders: dict[str, CandleBuilder] = {tf: CandleBuilder(tf) for tf in TIMEFRAMES}
engines: dict[str, SignalEngine] = {
    tf: SignalEngine(
        tf,
        settings.sl_method,
        fast_ema_period=settings.fast_ema_period,
        slow_ema_period=settings.slow_ema_period,
        atr_multiplier=settings.atr_multiplier,
        risk_reward=settings.risk_reward,
    )
    for tf in TIMEFRAMES
}
connected_clients: list[WebSocket] = []
_event_loop: asyncio.AbstractEventLoop | None = None
_live_feed_task: asyncio.Task | None = None

FUTURES_PRICE_MAX_AGE_SECONDS = 10
_latest_futures_price = {"value": 0.0, "at": None}
_last_tick_at: dict[str, datetime | None] = {"value": None}

RECONNECT_BACKOFF_SECONDS = [1, 2, 5, 10, 30]


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


def _handle_feed_message(message: object) -> None:
    """Route one parsed feed message into the tick pipeline.

    DhanFeed.process_data() returns a dict for ticker/quote/full packets
    (keys: "security_id" as int, "LTP" as a formatted string), a plain string
    for market-status packets, and None for server-disconnection packets
    (which instead set feed.on_close). Only dict ticker-style payloads with
    an LTP are actionable here.
    """
    if not isinstance(message, dict):
        return
    ltp = message.get("LTP")
    security_id = message.get("security_id")
    if ltp is None or security_id is None:
        return
    price = float(ltp)
    now = datetime.now()
    _last_tick_at["value"] = now
    if str(security_id) == settings.nifty_fut_security_id:
        _latest_futures_price["value"] = price
        _latest_futures_price["at"] = now
    elif str(security_id) == NIFTY_INDEX_SECURITY_ID:
        fut = _latest_futures_price
        fut_is_fresh = (
            fut["at"] is not None
            and (now - fut["at"]).total_seconds() <= FUTURES_PRICE_MAX_AGE_SECONDS
        )
        futures_price = fut["value"] if fut_is_fresh else price
        on_index_tick(now, price, futures_price)


async def run_live_feed() -> None:
    """Consume Dhan's live tick feed and reconnect with backoff on disconnect.

    Runs for the lifetime of the app; market-closed is just a normal no-data
    state handled by the same backoff loop. The installed dhanhq SDK's
    DhanFeed is asyncio-native (connect() and get_instrument_data() are
    coroutines), so we await them directly on the app's event loop instead of
    using the SDK's blocking run_forever() wrapper. Everything here therefore
    runs on the event loop thread, and calling on_index_tick() directly
    satisfies its same-thread sqlite constraint.
    """
    if not settings.dhan_client_id or not settings.dhan_access_token:
        logger.warning("Dhan credentials missing — live feed disabled")
        return
    instruments = [(marketfeed.IDX, NIFTY_INDEX_SECURITY_ID, marketfeed.Ticker)]
    if settings.nifty_fut_security_id:
        instruments.append((marketfeed.NSE_FNO, settings.nifty_fut_security_id, marketfeed.Ticker))
    else:
        logger.warning("NIFTY_FUT_SECURITY_ID not set — using index price as futures reference")
    attempt = 0
    while True:
        feed = None
        try:
            feed = marketfeed.DhanFeed(
                settings.dhan_client_id,
                settings.dhan_access_token,
                instruments,
                version="v2",
            )
            await feed.connect()
            logger.info("Dhan live feed connected")
            while True:
                message = await feed.get_instrument_data()
                if getattr(feed, "on_close", False):
                    raise ConnectionError("Dhan server requested disconnect")
                _handle_feed_message(message)
                attempt = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            delay = RECONNECT_BACKOFF_SECONDS[min(attempt, len(RECONNECT_BACKOFF_SECONDS) - 1)]
            attempt += 1
            logger.exception("Live feed error — reconnecting in %ss", delay)
            await asyncio.sleep(delay)
        finally:
            if feed is not None and feed.ws is not None:
                try:
                    await feed.ws.close()
                except Exception:
                    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop, _live_feed_task
    _event_loop = asyncio.get_running_loop()
    await backfill()
    _live_feed_task = asyncio.create_task(run_live_feed())
    yield
    _live_feed_task.cancel()
    try:
        await _live_feed_task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)


def _candle_to_json(c) -> dict:
    return {
        "timestamp": c.timestamp.isoformat(),
        "open": c.open, "high": c.high, "low": c.low, "close": c.close,
    }


@app.get("/status")
async def status() -> dict:
    last = _last_tick_at["value"]
    return {"last_tick_at": last.isoformat() if last else None}


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
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)


async def broadcast(message: dict) -> None:
    dead = []
    for client in list(connected_clients):
        try:
            await client.send_text(json.dumps(message))
        except Exception:
            dead.append(client)
    for client in dead:
        if client in connected_clients:
            connected_clients.remove(client)
            logger.warning("Pruned dead WebSocket client")


def _schedule_broadcast(message: dict) -> None:
    if _event_loop is not None:
        asyncio.run_coroutine_threadsafe(broadcast(message), _event_loop)


def on_index_tick(timestamp: datetime, price: float, futures_price: float, volume: float = 0.0) -> None:
    """Feed one Nifty 50 index tick into every timeframe's candle builder and signal engine.

    Thread-safety constraints:
    - DB writes: must be called from the same thread that called init_db()/created the
      app's sqlite3 connection — sqlite3 connections are not thread-safe by default
      (check_same_thread=True).
    - Broadcast scheduling: safe from any thread — the WebSocket broadcast is scheduled
      onto the app's event loop via asyncio.run_coroutine_threadsafe.
    If a live tick feed (Task 10) calls this from a foreign thread, route the entire
    call through the event loop instead, e.g.
    _event_loop.call_soon_threadsafe(on_index_tick, ts, price, fut_price, vol),
    so the sqlite write also happens on the loop thread."""
    for tf in TIMEFRAMES:
        closed = builders[tf].add_tick(timestamp, price, volume)
        live = builders[tf].candles[-1]
        _schedule_broadcast({
            "type": "candle",
            "timeframe": tf,
            "candle": _candle_to_json(live),
        })
        if closed:
            signal = engines[tf].evaluate(builders[tf].candles, futures_price)
            if signal:
                insert_signal(db_conn, signal)
                _schedule_broadcast({
                    "type": "signal",
                    "timeframe": tf,
                    "direction": signal.direction,
                    "timestamp": signal.timestamp.isoformat(),
                    "entry_index_price": signal.entry_index_price,
                    "entry_futures_price": signal.entry_futures_price,
                    "stop_loss": signal.stop_loss,
                    "target": signal.target,
                    "rr": signal.rr,
                })


app.mount(
    "/",
    StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "frontend"), html=True),
    name="frontend",
)

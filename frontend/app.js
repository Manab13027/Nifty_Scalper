const chartEl = document.getElementById("chart");
const chart = LightweightCharts.createChart(chartEl, {
  autoSize: true,
  layout: { background: { color: "#fff" }, textColor: "#000" },
  timeScale: { timeVisible: true },
});
const candleSeries = chart.addCandlestickSeries();
const emaFastSeries = chart.addLineSeries({ color: "#2962ff", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
const emaSlowSeries = chart.addLineSeries({ color: "#f57c00", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
const vwapSeries = chart.addLineSeries({ color: "#9c27b0", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });

const state = {
  activeTimeframe: "1m",
  candlesByTimeframe: {},
  markersByTimeframe: {},
  indicatorsByTimeframe: {},
};

// Backend sends naive local-time ISO strings; new Date() parses them as local time, which is correct for this same-machine tool. Don't append "Z".
function toSeriesData(candles) {
  return candles.map((c) => ({
    time: Math.floor(new Date(c.timestamp).getTime() / 1000),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

function toLineData(candles, values) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    if (values && values[i] != null) {
      out.push({ time: Math.floor(new Date(candles[i].timestamp).getTime() / 1000), value: values[i] });
    }
  }
  return out;
}

function renderActiveTimeframe() {
  const candles = state.candlesByTimeframe[state.activeTimeframe] || [];
  candleSeries.setData(toSeriesData(candles));
  candleSeries.setMarkers(state.markersByTimeframe[state.activeTimeframe] || []);
  const indicators = state.indicatorsByTimeframe[state.activeTimeframe] || {};
  emaFastSeries.setData(toLineData(candles, indicators.ema_fast));
  emaSlowSeries.setData(toLineData(candles, indicators.ema_slow));
  vwapSeries.setData(toLineData(candles, indicators.vwap));
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.activeTimeframe = btn.dataset.tf;
    renderActiveTimeframe();
  });
});

let audioCtx;
function beep() {
  audioCtx ??= new (window.AudioContext || window.webkitAudioContext)();
  audioCtx.resume();
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  gain.gain.value = 0.3;
  osc.frequency.value = 880;
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  osc.start();
  osc.stop(audioCtx.currentTime + 0.15);
}

function addSignalToPanel(signal) {
  const list = document.getElementById("signal-list");
  const item = document.createElement("li");
  item.className = signal.direction === "BUY" ? "buy" : "sell";
  item.textContent = `[${signal.timeframe}] ${signal.direction} @ ${signal.entry_futures_price.toFixed(2)} | SL ${signal.stop_loss.toFixed(2)} | Target ${signal.target.toFixed(2)} | RR 1:${signal.rr}`;
  list.prepend(item);
}

const ws = new WebSocket(`ws://${window.location.host}/ws`);

ws.onclose = () => {
  document.title = "⚠ DISCONNECTED — Nifty Scalper";
  document.body.style.opacity = "0.5";
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "history") {
    state.candlesByTimeframe[message.timeframe] = message.candles;
    state.markersByTimeframe[message.timeframe] = [];
    state.indicatorsByTimeframe[message.timeframe] = message.indicators || { ema_fast: [], ema_slow: [], vwap: [] };
    if (message.timeframe === state.activeTimeframe) renderActiveTimeframe();
  } else if (message.type === "candle") {
    const candles = state.candlesByTimeframe[message.timeframe] || [];
    const last = candles[candles.length - 1];
    const isNewBar = !(last && last.timestamp === message.candle.timestamp);
    if (isNewBar) {
      candles.push(message.candle);
    } else {
      candles[candles.length - 1] = message.candle;
    }
    state.candlesByTimeframe[message.timeframe] = candles;
    const indicators = state.indicatorsByTimeframe[message.timeframe]
      ?? (state.indicatorsByTimeframe[message.timeframe] = { ema_fast: [], ema_slow: [], vwap: [] });
    if (message.indicators) {
      for (const key of ["ema_fast", "ema_slow", "vwap"]) {
        const values = indicators[key] ?? (indicators[key] = []);
        if (isNewBar) {
          values.push(message.indicators[key]);
        } else {
          values[values.length - 1] = message.indicators[key];
        }
      }
    }
    if (message.timeframe === state.activeTimeframe) {
      // update() is cheaper than setData() for single-bar changes
      candleSeries.update(toSeriesData([message.candle])[0]);
      if (message.indicators) {
        const time = Math.floor(new Date(message.candle.timestamp).getTime() / 1000);
        if (message.indicators.ema_fast != null) emaFastSeries.update({ time, value: message.indicators.ema_fast });
        if (message.indicators.ema_slow != null) emaSlowSeries.update({ time, value: message.indicators.ema_slow });
        if (message.indicators.vwap != null) vwapSeries.update({ time, value: message.indicators.vwap });
      }
    }
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

const STALE_THRESHOLD_SECONDS = 60;
const STATUS_POLL_INTERVAL_MS = 5000;

async function pollStatus() {
  const el = document.getElementById("status-indicator");
  try {
    const res = await fetch("/status");
    const { last_tick_at } = await res.json();
    if (!last_tick_at) {
      el.textContent = "no data yet";
      return;
    }
    const secondsAgo = (Date.now() - new Date(last_tick_at).getTime()) / 1000;
    el.textContent = secondsAgo > STALE_THRESHOLD_SECONDS ? `stale (${Math.floor(secondsAgo)}s ago)` : "live";
  } catch {
    el.textContent = "disconnected";
  }
}
setInterval(pollStatus, STATUS_POLL_INTERVAL_MS);
pollStatus();

async function loadRecentSignals() {
  try {
    const res = await fetch("/signals");
    const signals = await res.json();
    // /signals returns newest-first; addSignalToPanel prepends, so reverse to keep newest at top.
    for (const s of signals.reverse()) addSignalToPanel(s);
  } catch {
    /* backend unavailable; sidebar stays empty */
  }
}
loadRecentSignals();

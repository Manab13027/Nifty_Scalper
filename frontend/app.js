const chartEl = document.getElementById("chart");
const chart = LightweightCharts.createChart(chartEl, {
  autoSize: true,
  layout: { background: { color: "#fff" }, textColor: "#000" },
  timeScale: { timeVisible: true },
});
const candleSeries = chart.addCandlestickSeries();

const state = {
  activeTimeframe: "1m",
  candlesByTimeframe: {},
  markersByTimeframe: {},
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

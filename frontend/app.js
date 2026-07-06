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

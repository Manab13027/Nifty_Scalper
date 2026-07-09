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
  mode: "live", // "live" | "backtest"
  backtest: null, // last /backtest response
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

document.querySelectorAll(".tab-btn[data-tf]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.mode = "live";
    state.activeTimeframe = btn.dataset.tf;
    document.getElementById("backtest-bar").hidden = true;
    document.getElementById("backtest-stats").hidden = true;
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
  const isVisible = (tf) => state.mode === "live" && tf === state.activeTimeframe;
  if (message.type === "history") {
    state.candlesByTimeframe[message.timeframe] = message.candles;
    state.markersByTimeframe[message.timeframe] = [];
    state.indicatorsByTimeframe[message.timeframe] = message.indicators || { ema_fast: [], ema_slow: [], vwap: [] };
    if (isVisible(message.timeframe)) renderActiveTimeframe();
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
    if (isVisible(message.timeframe)) {
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
    if (isVisible(message.timeframe)) renderActiveTimeframe();
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

// ---- Backtest mode ----

const backtestTab = document.getElementById("backtest-tab");
const backtestBar = document.getElementById("backtest-bar");
const backtestStatsEl = document.getElementById("backtest-stats");
const btStatus = document.getElementById("bt-status");

backtestTab.addEventListener("click", () => {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  backtestTab.classList.add("active");
  state.mode = "backtest";
  backtestBar.hidden = false;
  if (state.backtest) {
    renderBacktest(state.backtest);
  }
});

function toTime(iso) {
  return Math.floor(new Date(iso).getTime() / 1000);
}

function backtestMarkers(trades) {
  const markers = [];
  for (const t of trades) {
    markers.push({
      time: toTime(t.entry_time),
      position: t.direction === "BUY" ? "belowBar" : "aboveBar",
      color: t.direction === "BUY" ? "#16a34a" : "#dc2626",
      shape: t.direction === "BUY" ? "arrowUp" : "arrowDown",
      text: `${t.direction} SL ${t.stop_loss.toFixed(0)} / TG ${t.target.toFixed(0)}`,
    });
    if (t.exit_time) {
      const won = t.outcome === "win";
      markers.push({
        time: toTime(t.exit_time),
        position: "aboveBar",
        color: won ? "#16a34a" : "#dc2626",
        shape: "circle",
        text: won ? `WIN +${t.r_multiple}R` : `LOSS ${t.r_multiple}R`,
      });
    }
  }
  // lightweight-charts requires markers sorted by time
  markers.sort((a, b) => a.time - b.time);
  return markers;
}

function renderBacktest(bt) {
  candleSeries.setData(toSeriesData(bt.candles));
  candleSeries.setMarkers(backtestMarkers(bt.trades));
  // Overlays reflect live indicator state, not the backtest range — clear them.
  emaFastSeries.setData([]);
  emaSlowSeries.setData([]);
  vwapSeries.setData([]);
  chart.timeScale().fitContent();

  const s = bt.stats;
  backtestStatsEl.hidden = false;
  backtestStatsEl.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = `Backtest ${bt.from_date} → ${bt.to_date} (${bt.timeframe})`;
  backtestStatsEl.appendChild(title);
  const lines = [
    `Signals: ${s.total_signals} | Trades taken: ${s.trades}`,
    `Wins: ${s.wins} | Losses: ${s.losses} | Open: ${s.open}`,
    `Win rate: ${s.win_rate == null ? "n/a" : (s.win_rate * 100).toFixed(1) + "%"}`,
  ];
  for (const text of lines) {
    const div = document.createElement("div");
    div.textContent = text;
    backtestStatsEl.appendChild(div);
  }
  const totalR = document.createElement("div");
  const rSpan = document.createElement("span");
  rSpan.className = s.total_r >= 0 ? "stat-good" : "stat-bad";
  rSpan.textContent = `${s.total_r >= 0 ? "+" : ""}${s.total_r.toFixed(1)}R`;
  totalR.append("Net result: ", rSpan);
  backtestStatsEl.appendChild(totalR);
}

document.getElementById("bt-run").addEventListener("click", async () => {
  const from = document.getElementById("bt-from").value;
  const to = document.getElementById("bt-to").value;
  const timeframe = document.getElementById("bt-timeframe").value;
  if (!from || !to) {
    btStatus.textContent = "pick both dates";
    return;
  }
  btStatus.textContent = "running…";
  try {
    const res = await fetch(`/backtest?from_date=${from}&to_date=${to}&timeframe=${timeframe}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      btStatus.textContent = err.detail || `error ${res.status}`;
      return;
    }
    state.backtest = await res.json();
    btStatus.textContent = `${state.backtest.candles.length} candles`;
    renderBacktest(state.backtest);
  } catch {
    btStatus.textContent = "request failed";
  }
});

// Default the date pickers to the last 5 days.
(() => {
  const today = new Date();
  const past = new Date(today.getTime() - 5 * 86400000);
  const fmt = (d) => d.toISOString().slice(0, 10);
  document.getElementById("bt-to").value = fmt(today);
  document.getElementById("bt-from").value = fmt(past);
})();

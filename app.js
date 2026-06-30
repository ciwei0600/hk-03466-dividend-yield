const DATA_URL = "./assets/03466_ttm_dividend_yield_daily_annualized.csv";

const chart = document.querySelector("#yieldChart");
const readout = document.querySelector("#pointReadout");

let rows = [];
let selectedIndex = -1;

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines.shift().split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
}

function toNumber(value) {
  if (String(value ?? "").trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatPercent(value) {
  return `${value.toFixed(2)}%`;
}

function formatHkd(value) {
  return `${value.toFixed(2)} HKD`;
}

function makeSvgElement(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
  return el;
}

function updateReadout(row) {
  if (!row) return;
  readout.querySelector('[data-field="trade_date"]').textContent = row.tradeDate;
  readout.querySelector('[data-field="close"]').textContent = formatHkd(row.close);
  readout.querySelector('[data-field="annualized_dividend_hkd"]').textContent = formatHkd(row.annualizedDividend);
  readout.querySelector('[data-field="annualized_dividend_yield_pct"]').textContent = formatPercent(row.yieldPct);
}

function getNearestIndex(x, points) {
  let nearest = 0;
  let best = Number.POSITIVE_INFINITY;
  points.forEach((point, index) => {
    const distance = Math.abs(point.x - x);
    if (distance < best) {
      best = distance;
      nearest = index;
    }
  });
  return nearest;
}

function renderChart() {
  if (!chart || !rows.length) return;

  const container = chart.parentElement;
  const width = Math.max(container.clientWidth, 320);
  const height = width < 620 ? 360 : 520;
  const margin = width < 620
    ? { top: 24, right: 18, bottom: 48, left: 48 }
    : { top: 28, right: 30, bottom: 56, left: 64 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const minTime = rows[0].date.getTime();
  const maxTime = rows.at(-1).date.getTime();
  const values = rows.map((row) => row.yieldPct);
  const minY = Math.floor(Math.min(...values) - 0.4);
  const maxY = Math.ceil(Math.max(...values) + 0.4);
  const xScale = (date) => margin.left + ((date.getTime() - minTime) / (maxTime - minTime)) * plotWidth;
  const yScale = (value) => margin.top + ((maxY - value) / (maxY - minY)) * plotHeight;
  const points = rows.map((row) => ({ x: xScale(row.date), y: yScale(row.yieldPct) }));

  chart.textContent = "";
  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("width", "100%");
  chart.setAttribute("height", String(height));

  const grid = makeSvgElement("g", { class: "chart-grid" });
  const axis = makeSvgElement("g", { class: "chart-axis" });
  const yTicks = 5;
  for (let i = 0; i <= yTicks; i += 1) {
    const value = minY + ((maxY - minY) / yTicks) * i;
    const y = yScale(value);
    grid.appendChild(makeSvgElement("line", {
      x1: margin.left,
      x2: width - margin.right,
      y1: y,
      y2: y,
    }));
    const label = makeSvgElement("text", {
      x: margin.left - 10,
      y: y + 4,
      "text-anchor": "end",
    });
    label.textContent = `${value.toFixed(1)}%`;
    axis.appendChild(label);
  }

  const seenMonths = new Set();
  const monthTicks = rows.filter((row) => {
    const month = row.tradeDate.slice(0, 7);
    if (seenMonths.has(month)) return false;
    seenMonths.add(month);
    return true;
  });
  const stride = width < 620 ? 3 : 2;
  monthTicks.forEach((row, index) => {
    if (index % stride !== 0) return;
    const x = xScale(row.date);
    grid.appendChild(makeSvgElement("line", {
      x1: x,
      x2: x,
      y1: margin.top,
      y2: height - margin.bottom,
    }));
    const label = makeSvgElement("text", {
      x,
      y: height - 18,
      "text-anchor": "middle",
    });
    label.textContent = row.tradeDate.slice(0, 7);
    axis.appendChild(label);
  });

  const areaPath = [
    `M ${points[0].x} ${height - margin.bottom}`,
    ...points.map((point) => `L ${point.x} ${point.y}`),
    `L ${points.at(-1).x} ${height - margin.bottom}`,
    "Z",
  ].join(" ");
  chart.appendChild(grid);
  chart.appendChild(makeSvgElement("path", { class: "chart-area", d: areaPath }));

  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  chart.appendChild(makeSvgElement("path", { class: "chart-line", d: linePath }));
  chart.appendChild(axis);

  const overlay = makeSvgElement("rect", {
    class: "chart-overlay",
    x: margin.left,
    y: margin.top,
    width: plotWidth,
    height: plotHeight,
  });
  overlay.addEventListener("click", (event) => {
    const rect = chart.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    selectedIndex = getNearestIndex(svgX, points);
    updateReadout(rows[selectedIndex]);
    renderChart();
  });
  chart.appendChild(overlay);

  const hitLayer = makeSvgElement("g", { class: "hit-layer" });
  points.forEach((point, index) => {
    const hit = makeSvgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: 7,
      tabindex: 0,
      role: "button",
      "aria-label": `${rows[index].tradeDate} ${formatPercent(rows[index].yieldPct)}`,
    });
    hit.addEventListener("click", () => {
      selectedIndex = index;
      updateReadout(rows[selectedIndex]);
      renderChart();
    });
    hit.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectedIndex = index;
        updateReadout(rows[selectedIndex]);
        renderChart();
      }
    });
    hitLayer.appendChild(hit);
  });
  chart.appendChild(hitLayer);

  const selected = points[selectedIndex];
  chart.appendChild(makeSvgElement("line", {
    class: "selected-guide",
    x1: selected.x,
    x2: selected.x,
    y1: margin.top,
    y2: height - margin.bottom,
  }));
  chart.appendChild(makeSvgElement("circle", {
    class: "selected-point",
    cx: selected.x,
    cy: selected.y,
    r: 6,
  }));
}

async function init() {
  const response = await fetch(DATA_URL);
  const csv = await response.text();
  rows = parseCsv(csv)
    .map((row) => ({
      tradeDate: row.trade_date,
      date: new Date(`${row.trade_date}T00:00:00+08:00`),
      close: toNumber(row.close),
      annualizedDividend: toNumber(row.annualized_dividend_hkd),
      yieldPct: toNumber(row.annualized_dividend_yield_pct),
    }))
    .filter((row) => row.close !== null && row.annualizedDividend !== null && row.yieldPct !== null);
  selectedIndex = rows.length - 1;
  updateReadout(rows[selectedIndex]);
  renderChart();
  window.addEventListener("resize", renderChart);
}

init().catch((error) => {
  console.error(error);
  if (readout) {
    readout.querySelector('[data-field="trade_date"]').textContent = "加载失败";
  }
});

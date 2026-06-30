const DATA_SOURCES = [
  {
    daily: "./runtime-data/03466_ttm_dividend_yield_daily_annualized.csv",
    dividends: "./runtime-data/03466_dividends_source_hsi.csv",
  },
  {
    daily: "./assets/03466_ttm_dividend_yield_daily_annualized.csv",
    dividends: "./assets/03466_dividends_source_hsi.csv",
  },
];

const chart = document.querySelector("#yieldChart");
const readout = document.querySelector("#pointReadout");
const dailyCsvLink = document.querySelector("#dailyCsvLink");
const dividendCsvLink = document.querySelector("#dividendCsvLink");

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

function updateLatestMetrics(row) {
  if (!row) return;
  document.querySelector('[data-latest-field="trade_date"]').textContent = row.tradeDate;
  document.querySelector('[data-latest-field="close"]').textContent = formatHkd(row.close);
  document.querySelector('[data-latest-field="annualized_dividend_hkd"]').textContent = formatHkd(row.annualizedDividend);
  document.querySelector('[data-latest-field="annualized_dividend_yield_pct"]').textContent = formatPercent(row.yieldPct);
}

async function fetchFirstAvailableCsv() {
  for (const source of DATA_SOURCES) {
    try {
      const response = await fetch(source.daily, { cache: "no-store" });
      if (!response.ok) continue;
      return { csv: await response.text(), source };
    } catch (error) {
      console.warn(`failed to load ${source.daily}`, error);
    }
  }
  throw new Error("No dividend yield CSV source is available");
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

function paddedRange(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  return {
    min: min - span * 0.08,
    max: max + span * 0.08,
  };
}

function renderChart() {
  if (!chart || !rows.length) return;

  const container = chart.parentElement;
  const width = Math.max(container.clientWidth, 320);
  const height = width < 620 ? 360 : 520;
  const margin = width < 620
    ? { top: 34, right: 48, bottom: 48, left: 48 }
    : { top: 38, right: 76, bottom: 56, left: 64 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const minTime = rows[0].date.getTime();
  const maxTime = rows.at(-1).date.getTime();
  const yieldValues = rows.map((row) => row.yieldPct);
  const priceValues = rows.map((row) => row.close);
  const yieldRange = paddedRange(yieldValues);
  const priceRange = paddedRange(priceValues);
  const minYield = Math.floor(yieldRange.min * 10) / 10;
  const maxYield = Math.ceil(yieldRange.max * 10) / 10;
  const minPrice = Math.floor(priceRange.min);
  const maxPrice = Math.ceil(priceRange.max);
  const xScale = (date) => margin.left + ((date.getTime() - minTime) / (maxTime - minTime)) * plotWidth;
  const yieldScale = (value) => margin.top + ((maxYield - value) / (maxYield - minYield)) * plotHeight;
  const priceScale = (value) => margin.top + ((maxPrice - value) / (maxPrice - minPrice)) * plotHeight;
  const yieldPoints = rows.map((row) => ({ x: xScale(row.date), y: yieldScale(row.yieldPct) }));
  const pricePoints = rows.map((row) => ({ x: xScale(row.date), y: priceScale(row.close) }));

  chart.textContent = "";
  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("width", "100%");
  chart.setAttribute("height", String(height));

  const grid = makeSvgElement("g", { class: "chart-grid" });
  const axis = makeSvgElement("g", { class: "chart-axis" });
  const yTicks = 5;
  for (let i = 0; i <= yTicks; i += 1) {
    const yieldValue = minYield + ((maxYield - minYield) / yTicks) * i;
    const priceValue = minPrice + ((maxPrice - minPrice) / yTicks) * i;
    const y = yieldScale(yieldValue);
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
    label.textContent = `${yieldValue.toFixed(1)}%`;
    axis.appendChild(label);

    const priceLabel = makeSvgElement("text", {
      class: "price-axis",
      x: width - margin.right + 10,
      y: y + 4,
      "text-anchor": "start",
    });
    priceLabel.textContent = priceValue.toFixed(1);
    axis.appendChild(priceLabel);
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

  const legend = makeSvgElement("g", { class: "chart-legend" });
  const legendX = margin.left;
  const legendY = 14;
  legend.appendChild(makeSvgElement("line", {
    class: "legend-yield",
    x1: legendX,
    x2: legendX + 22,
    y1: legendY,
    y2: legendY,
  }));
  const yieldLegend = makeSvgElement("text", { x: legendX + 28, y: legendY + 4 });
  yieldLegend.textContent = "股息率";
  legend.appendChild(yieldLegend);
  const priceLegendX = legendX + 96;
  legend.appendChild(makeSvgElement("line", {
    class: "legend-price",
    x1: priceLegendX,
    x2: priceLegendX + 22,
    y1: legendY,
    y2: legendY,
  }));
  const priceLegend = makeSvgElement("text", { x: priceLegendX + 28, y: legendY + 4 });
  priceLegend.textContent = "收盘价";
  legend.appendChild(priceLegend);
  chart.appendChild(legend);

  const areaPath = [
    `M ${yieldPoints[0].x} ${height - margin.bottom}`,
    ...yieldPoints.map((point) => `L ${point.x} ${point.y}`),
    `L ${yieldPoints.at(-1).x} ${height - margin.bottom}`,
    "Z",
  ].join(" ");
  chart.appendChild(grid);
  chart.appendChild(makeSvgElement("path", { class: "chart-area", d: areaPath }));

  const yieldPath = yieldPoints.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const pricePath = pricePoints.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  chart.appendChild(makeSvgElement("path", { class: "chart-line chart-line-yield", d: yieldPath }));
  chart.appendChild(makeSvgElement("path", { class: "chart-line chart-line-price", d: pricePath }));
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
    selectedIndex = getNearestIndex(svgX, yieldPoints);
    updateReadout(rows[selectedIndex]);
    renderChart();
  });
  chart.appendChild(overlay);

  const hitLayer = makeSvgElement("g", { class: "hit-layer" });
  yieldPoints.forEach((point, index) => {
    const hit = makeSvgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: 7,
      tabindex: 0,
      role: "button",
      "aria-label": `${rows[index].tradeDate} ${formatPercent(rows[index].yieldPct)} ${formatHkd(rows[index].close)}`,
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

  const selected = yieldPoints[selectedIndex];
  const selectedPrice = pricePoints[selectedIndex];
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
  chart.appendChild(makeSvgElement("circle", {
    class: "selected-price-point",
    cx: selectedPrice.x,
    cy: selectedPrice.y,
    r: 5,
  }));
}

async function init() {
  const { csv, source } = await fetchFirstAvailableCsv();
  if (dailyCsvLink) dailyCsvLink.href = source.daily;
  if (dividendCsvLink) dividendCsvLink.href = source.dividends;
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
  updateLatestMetrics(rows[selectedIndex]);
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

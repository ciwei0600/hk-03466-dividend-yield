const FUNDS = {
  "03466": {
    name: "03466.HK · 恒生高息股 30 ETF", currency: "HKD", decimals: 2,
    daily: "03466_ttm_dividend_yield_daily_annualized.csv", dividends: "03466_dividends_source_hsi.csv",
    summary: "summary.json", constituents: "03466_hshd30_constituents_hsi.csv", constituentsSummary: "constituents_summary.json",
    dividendField: "annualized_dividend_hkd", yieldField: "annualized_dividend_yield_pct", count: 30,
    index: "HSHD30 · 恒生高息股 30", dividendLabel: "年化股息 / 份", yieldLabel: "年化股息率",
    calculation: "03466：按除息日取最近最多 12 次月度分派；不足 12 次时，用最近一次月息补足，再除以当日未复权收盘价。金额单位为港元／份；首次除息前不绘制股息率。",
  },
  "515080": {
    name: "515080.SH · 招商中证红利 ETF", currency: "CNY", decimals: 3,
    daily: "515080_ttm_dividend_yield_daily.csv", dividends: "515080_dividends_source_cmf.csv",
    summary: "515080_summary.json", constituents: "515080_csi_dividend_constituents.csv", constituentsSummary: "515080_constituents_summary.json",
    dividendField: "ttm_dividend_cny", yieldField: "ttm_dividend_yield_pct", count: 100,
    index: "000922 · 中证红利", dividendLabel: "折算 TTM 股息 / 份", yieldLabel: "折算 TTM 股息率",
    calculationMethod: "frequency_adjusted_ttm_v1",
    calculation: "515080：按分红频率折算年度股息，再除以当日未复权收盘价。自 2024-03-28 起取最近 4 次已除息的季度分红；2021-06-18 至 2024-03-27 取最近 2 次半年分红；更早取最近 1 次年度分红。同一频率阶段不足相应次数时，按最近一次同频分红补足估算，不混用半年与季度金额。每 10 份金额除以 10 换算成人民币／份；首次除息前留空。该折算 TTM 口径不按除息周年剔除旧分红；严格过去 365 天实际分红另保留在下载 CSV 的 actual_365d 字段中。",
  },
};
let activeFundId = "03466";
let activeFund = FUNDS[activeFundId];
let loadToken = 0;
function dataSources(fund) {
  return ["runtime-data", "assets"].map((directory) => Object.fromEntries(
    ["daily", "dividends", "summary", "constituents", "constituentsSummary"].map((key) => [key, `./${directory}/${fund[key]}`]),
  ));
}

const chart = document.querySelector("#yieldChart");
const readout = document.querySelector("#pointReadout");
const dailyCsvLink = document.querySelector("#dailyCsvLink");
const dividendCsvLink = document.querySelector("#dividendCsvLink");
const constituentCsvLink = document.querySelector("#constituentCsvLink");
const constituentTableBody = document.querySelector("#constituentTableBody");
const constituentStatus = document.querySelector("#constituentStatus");
const constituentCount = document.querySelector("#constituentCount");
const constituentUpdatedAt = document.querySelector("#constituentUpdatedAt");
const holdingsAsOf = document.querySelector("#holdingsAsOf");
const constituentSyncedAt = document.querySelector("#constituentSyncedAt");
const constituentChanges = document.querySelector("#constituentChanges");

let rows = [];
let selectedIndex = -1;
let viewStart = 0;
let viewEnd = -1;
const dateControls = document.querySelector("#dateControls");
const dateSlider = document.querySelector("#dateSlider");
const dateNavigator = document.querySelector("#dateNavigator");
const dateWindow = document.querySelector("#dateWindow");
const dateStartHandle = document.querySelector("#dateStartHandle");
const dateEndHandle = document.querySelector("#dateEndHandle");
const previousDate = document.querySelector("#previousDate");
const nextDate = document.querySelector("#nextDate");

function presetStart(months) {
  if (months === "all") return 0;
  const [year, month, day] = rows.at(-1).tradeDate.split("-").map(Number);
  const start = new Date(Date.UTC(year, month - 1 - Number(months), 1));
  const lastDay = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
  start.setUTCDate(Math.min(day, lastDay));
  const cutoff = start.toISOString().slice(0, 10);
  return Math.max(0, Math.min(rows.findIndex((row) => row.tradeDate >= cutoff), rows.length - 2));
}

function syncDateControls() {
  if (!rows.length) return;
  const last = rows.length - 1;
  const left = (viewStart / (last || 1)) * 100;
  const right = last ? (viewEnd / last) * 100 : 100;
  document.querySelector("#dateRangeLabel").textContent = `${rows[viewStart].tradeDate} — ${rows[viewEnd].tradeDate}`;
  dateWindow.style.left = `${left}%`;
  dateWindow.style.width = `${right - left}%`;
  dateWindow.setAttribute("aria-label", `移动日期区间：${rows[viewStart].tradeDate} 至 ${rows[viewEnd].tradeDate}，左右方向键移动`);
  [[dateStartHandle, viewStart, 0, Math.max(0, viewEnd - 1), left],
    [dateEndHandle, viewEnd, Math.min(last, viewStart + 1), last, right]].forEach(([handle, value, min, max, position]) => {
    handle.style.left = `${position}%`;
    handle.setAttribute("aria-valuemin", min);
    handle.setAttribute("aria-valuemax", max);
    handle.setAttribute("aria-valuenow", value);
    handle.setAttribute("aria-valuetext", rows[value].tradeDate);
    handle.disabled = last === 0;
  });
  dateWindow.disabled = viewEnd - viewStart === last;
  dateSlider.min = viewStart;
  dateSlider.max = viewEnd;
  dateSlider.value = selectedIndex;
  dateSlider.setAttribute("aria-valuetext", rows[selectedIndex].tradeDate);
  document.querySelector("#selectedDateLabel").value = rows[selectedIndex].tradeDate;
  previousDate.disabled = selectedIndex <= viewStart;
  nextDate.disabled = selectedIndex >= viewEnd;
  document.querySelectorAll("[data-months]").forEach((button) => {
    button.setAttribute("aria-pressed", String(viewEnd === last && viewStart === presetStart(button.dataset.months)));
  });
}

function setDateRange(start, end) {
  if (!rows.length) return;
  const last = rows.length - 1;
  viewStart = Math.max(0, Math.min(Math.round(start), Math.max(0, last - 1)));
  viewEnd = Math.max(Math.min(last, viewStart + 1), Math.min(last, Math.round(end)));
  selectedIndex = Math.max(viewStart, Math.min(viewEnd, selectedIndex));
  updateReadout(rows[selectedIndex]);
  renderChart();
}

function selectDate(index) {
  if (!rows.length) return;
  selectedIndex = Math.max(viewStart, Math.min(viewEnd, index));
  updateReadout(rows[selectedIndex]);
  renderChart();
}

function initDateControls() {
  viewStart = 0;
  viewEnd = rows.length - 1;
  dateControls.disabled = false;
  document.querySelector("#dateFirst").textContent = rows[0].tradeDate;
  document.querySelector("#dateLast").textContent = rows.at(-1).tradeDate;
  const range = paddedRange(rows.map((row) => row.yieldPct));
  const path = rows.map((row, index) => `${index ? "L" : "M"} ${index / (viewEnd || 1) * 1000} ${44 - (row.yieldPct - range.min) / (range.max - range.min) * 40}`).join(" ");
  document.querySelector("#dateOverview").replaceChildren(makeSvgElement("path", { d: path }));
  syncDateControls();
}

dateSlider.addEventListener("input", () => selectDate(Number(dateSlider.value)));
previousDate.addEventListener("click", () => selectDate(selectedIndex - 1));
nextDate.addEventListener("click", () => selectDate(selectedIndex + 1));
document.querySelectorAll("[data-months]").forEach((button) => {
  button.addEventListener("click", () => {
    if (rows.length) setDateRange(presetStart(button.dataset.months), rows.length - 1);
  });
});

// Pointer capture keeps mouse and touch dragging attached to the same control.
[[dateStartHandle, "start"], [dateEndHandle, "end"], [dateWindow, "window"]].forEach(([element, kind]) => {
  let drag = null;
  element.addEventListener("pointerdown", (event) => {
    if (!rows.length || element.disabled || dateControls.disabled || event.button !== 0) return;
    event.preventDefault();
    element.focus();
    drag = { x: event.clientX, start: viewStart, end: viewEnd, token: loadToken, width: dateNavigator.clientWidth };
    element.setPointerCapture(event.pointerId);
  });
  element.addEventListener("pointermove", (event) => {
    if (!drag || drag.token !== loadToken || !rows.length) return;
    const delta = Math.round((event.clientX - drag.x) / drag.width * (rows.length - 1));
    if (kind === "start") setDateRange(Math.min(drag.end - 1, drag.start + delta), drag.end);
    else if (kind === "end") setDateRange(drag.start, Math.max(drag.start + 1, drag.end + delta));
    else {
      const shift = Math.max(-drag.start, Math.min(rows.length - 1 - drag.end, delta));
      setDateRange(drag.start + shift, drag.end + shift);
    }
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((name) => element.addEventListener(name, () => { drag = null; }));
  element.addEventListener("keydown", (event) => {
    if (!rows.length || element.disabled || dateControls.disabled) return;
    const steps = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -20, PageUp: 20 };
    if (!(event.key in steps) && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const last = rows.length - 1;
    if (kind === "window") {
      const shift = event.key === "Home" ? -viewStart : event.key === "End" ? last - viewEnd : Math.max(-viewStart, Math.min(last - viewEnd, steps[event.key]));
      setDateRange(viewStart + shift, viewEnd + shift);
    } else if (kind === "start") {
      setDateRange(event.key === "Home" ? 0 : event.key === "End" ? viewEnd - 1 : Math.min(viewEnd - 1, viewStart + steps[event.key]), viewEnd);
    } else {
      setDateRange(viewStart, event.key === "Home" ? viewStart + 1 : event.key === "End" ? last : Math.max(viewStart + 1, viewEnd + steps[event.key]));
    }
  });
});

function parseCsv(text) {
  const records = [];
  let record = [];
  let field = "";
  let quoted = false;
  const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  for (let index = 0; index < normalized.length; index += 1) {
    const char = normalized[index];
    if (quoted) {
      if (char === '"' && normalized[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      record.push(field);
      field = "";
    } else if (char === "\n") {
      record.push(field);
      if (record.some((value) => value !== "")) records.push(record);
      record = [];
      field = "";
    } else {
      field += char;
    }
  }
  record.push(field);
  if (record.some((value) => value !== "")) records.push(record);
  const headers = records.shift() || [];
  return records.map((values) => Object.fromEntries(
    headers.map((header, index) => [header, values[index] ?? ""]),
  ));
}

function toNumber(value) {
  if (String(value ?? "").trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatPercent(value) {
  return `${value.toFixed(2)}%`;
}

function formatCurrency(value) {
  return `${value.toFixed(activeFund.decimals)} ${activeFund.currency}`;
}

function makeSvgElement(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
  return el;
}

function updateReadout(row) {
  if (!row) return;
  readout.querySelector('[data-field="trade_date"]').textContent = row.tradeDate;
  readout.querySelector('[data-field="close"]').textContent = formatCurrency(row.close);
  readout.querySelector('[data-field="annualized_dividend"]').textContent = formatCurrency(row.annualizedDividend);
  readout.querySelector('[data-field="dividend_yield_pct"]').textContent = formatPercent(row.yieldPct);
  const basis = document.querySelector("#yieldBasisNote");
  basis.hidden = activeFundId !== "515080";
  if (!basis.hidden) {
    const frequency = { 1: "年度", 2: "半年", 4: "季度" }[row.dividendFrequency];
    const estimate = row.estimatedDividendCount ? `；另按最近一次金额补足 ${row.estimatedDividendCount} 次（估算）` : "；无补足估算";
    basis.textContent = `选中日期折算依据：最近 ${row.dividendCount} 次${frequency}分红${estimate}。最近除息日 ${row.dividendAsOf}。`;
  }
}

function updateLatestMetrics(row) {
  if (!row) return;
  document.querySelector('[data-latest-field="trade_date"]').textContent = row.tradeDate;
  document.querySelector('[data-latest-field="close"]').textContent = formatCurrency(row.close);
  document.querySelector('[data-latest-field="annualized_dividend"]').textContent = formatCurrency(row.annualizedDividend);
  document.querySelector('[data-latest-field="dividend_yield_pct"]').textContent = formatPercent(row.yieldPct);
}

async function fetchFirstAvailableCsv(fund) {
  for (const source of dataSources(fund)) {
    try {
      const [response, summaryResponse] = await Promise.all([
        fetch(source.daily, { cache: "no-store" }), fetch(source.summary, { cache: "no-store" }),
      ]);
      if (!response.ok || !summaryResponse.ok) continue;
      const csv = await response.text();
      const summary = await summaryResponse.json();
      if (fund.calculationMethod && summary.calculation_method !== fund.calculationMethod) continue;
      const records = parseCsv(csv);
      if (!records.length || records.at(-1).trade_date !== summary.latest.trade_date) continue;
      return { csv, source, summary };
    } catch (error) {
      console.warn(`failed to load ${source.daily}`, error);
    }
  }
  throw new Error("No dividend yield CSV source is available");
}

async function fetchConstituentSnapshot(fund) {
  for (const source of dataSources(fund)) {
    try {
      const [csvResponse, summaryResponse] = await Promise.all([
        fetch(source.constituents, { cache: "no-store" }),
        fetch(source.constituentsSummary, { cache: "no-store" }),
      ]);
      if (!csvResponse.ok || !summaryResponse.ok) continue;
      return {
        rows: parseCsv(await csvResponse.text()),
        summary: await summaryResponse.json(),
        source,
      };
    } catch (error) {
      console.warn(`failed to load ${source.constituents}`, error);
    }
  }
  throw new Error("No constituent snapshot is available");
}

function formatOfficialTime(value) {
  if (!value) return "-";
  return `${String(value).slice(0, 16)} HKT`;
}

function formatSyncedTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Hong_Kong",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(parsed).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} HKT`;
}

function formatSnapshotDate(value) {
  if (!value) return "-";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : String(value);
}

function formatConstituentList(items) {
  return items.map((item) => {
    const fullSymbol = item.full_symbol || `${item.symbol}.HK`;
    return `${fullSymbol} ${item.company_name_zh || item.name}`;
  }).join("、");
}

function formatConstituentChange(event) {
  const parts = [];
  const added = event.added || [];
  const removed = event.removed || [];
  if (added.length) parts.push(`新增：${formatConstituentList(added)}`);
  if (removed.length) parts.push(`剔除：${formatConstituentList(removed)}`);
  return parts.join("；");
}

function renderConstituentChanges(summary) {
  const added = summary.added_since_previous || [];
  const removed = summary.removed_since_previous || [];
  constituentChanges.classList.remove("has-change");
  constituentChanges.dataset.changeState = "none";
  if (added.length || removed.length) {
    constituentChanges.textContent = `本次同步发现成分股变更（官网资料时间 ${formatOfficialTime(summary.official_updated_at)}）：${formatConstituentChange({ added, removed })}`;
    constituentChanges.classList.add("has-change");
    constituentChanges.dataset.changeState = "current";
    return;
  }
  const latestChange = summary.latest_change;
  if (latestChange && ((latestChange.added || []).length || (latestChange.removed || []).length)) {
    constituentChanges.textContent = `本次同步无变化。最近一次变更（官网资料时间 ${formatOfficialTime(latestChange.official_updated_at)}）：${formatConstituentChange(latestChange)}`;
    constituentChanges.classList.add("has-change");
    constituentChanges.dataset.changeState = "history";
    return;
  }
  if (summary.comparison_basis === "none") {
    constituentChanges.textContent = "已建立首个官网基准快照，后续同步将自动记录新增与剔除。";
    constituentChanges.dataset.changeState = "baseline";
    return;
  }
  constituentChanges.textContent = "与上一次成功快照相比，未发现成分股变更。";
}

async function initConstituents(fund, token) {
  const snapshot = await fetchConstituentSnapshot(fund);
  if (token !== loadToken) return;
  const expectedCount = Number(snapshot.summary.expected_count || 30);
  const isSynced = snapshot.summary.sync_status === "synced"
    && snapshot.rows.length === expectedCount
    && snapshot.summary.count_matches_official === true
    && (fund.currency === "CNY" || (snapshot.summary.holdings_match_constituents === true
      && Number(snapshot.summary.holdings_count) === expectedCount
      && Number(snapshot.summary.profiles_count) === expectedCount));

  constituentStatus.textContent = isSynced ? "指数官网已同步" : "同步待核对";
  constituentStatus.classList.toggle("is-warning", !isSynced);
  constituentCount.textContent = `${snapshot.rows.length} / ${expectedCount}`;
  constituentUpdatedAt.textContent = formatOfficialTime(snapshot.summary.official_updated_at);
  holdingsAsOf.textContent = formatSnapshotDate(snapshot.summary.holdings_as_of);
  constituentSyncedAt.textContent = formatSyncedTime(snapshot.summary.synced_at);
  constituentCsvLink.href = snapshot.source.constituents;
  renderConstituentChanges(snapshot.summary);
  if (fund.currency === "CNY") {
    document.querySelector("#tableCaption").textContent = `按基金报告持仓比例排序。基金持仓为 ${snapshot.summary.holdings_as_of} 中期报告的指数投资部分，占净资产合计 ${snapshot.summary.holding_weight_total_pct}%；指数权重为 ${snapshot.summary.index_weights_as_of}，两者资料日期与口径不同。`;
    document.querySelector("#constituentSourceNote").innerHTML = `每天 07:10 CST 核对中证指数官网成分与变更。基金持仓按已核验定期报告披露日期展示，新报告更新前保留上次披露值；不代表实时持仓。<a href="${snapshot.summary.source_url}" target="_blank" rel="noopener">官方成分表</a> · <a href="${snapshot.summary.index_weight_source_url}" target="_blank" rel="noopener">官方指数权重</a> · <a href="${snapshot.summary.holdings_source_url}" target="_blank" rel="noopener">招商基金持仓报告</a>。行业来自 Data_Server；主营业务简介待补齐。`;
  }

  constituentTableBody.textContent = "";
  snapshot.rows.forEach((row, index) => {
    const tr = document.createElement("tr");

    const orderCell = document.createElement("td");
    orderCell.textContent = String(index + 1);
    tr.appendChild(orderCell);

    const symbolCell = document.createElement("td");
    symbolCell.className = "stock-code";
    symbolCell.textContent = row.full_symbol || `${row.symbol}.HK`;
    tr.appendChild(symbolCell);

    const weightCell = document.createElement("td");
    weightCell.className = "holding-weight";
    const weight = toNumber(row.weight_pct);
    weightCell.textContent = weight === null ? "未披露" : formatPercent(weight);
    tr.appendChild(weightCell);
    if (fund.currency === "CNY") {
      const indexWeightCell = document.createElement("td");
      indexWeightCell.className = "holding-weight";
      const weight = toNumber(row.index_weight_pct);
      indexWeightCell.textContent = weight === null ? "未披露" : `${weight.toFixed(3)}%`;
      tr.appendChild(indexWeightCell);
    }

    const companyCell = document.createElement("td");
    const companyName = document.createElement("strong");
    companyName.className = "company-name";
    companyName.textContent = row.company_name_zh || row.fund_name_zh || row.name;
    const companyNameEn = document.createElement("span");
    companyNameEn.className = "company-name-en";
    companyNameEn.textContent = row.name || row.fund_name;
    companyCell.append(companyName, companyNameEn);
    tr.appendChild(companyCell);

    const businessCell = document.createElement("td");
    businessCell.className = "business-summary";
    const businessText = document.createElement("span");
    businessText.textContent = fund.currency === "CNY" ? (row.industry_zh || "行业待补齐") : (row.business_summary || "-");
    businessCell.appendChild(businessText);
    if (row.industry_zh && fund.currency !== "CNY") {
      const industry = document.createElement("small");
      industry.textContent = `行业：${row.industry_zh}`;
      businessCell.appendChild(industry);
    }
    tr.appendChild(businessCell);

    constituentTableBody.appendChild(tr);
  });
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
  const span = Math.max(max - min, Math.abs(max) * 0.02, 0.01);
  return {
    min: min - span * 0.08,
    max: max + span * 0.08,
  };
}

function renderChart() {
  if (!chart || !rows.length) return;
  syncDateControls();
  const visibleRows = rows.slice(viewStart, viewEnd + 1);

  const container = chart.parentElement;
  const width = Math.max(container.clientWidth, 320);
  const isPhone = width < 420;
  const isCompact = width < 620;
  const height = isPhone ? 330 : isCompact ? 360 : 520;
  const margin = isPhone
    ? { top: 34, right: 42, bottom: 44, left: 42 }
    : isCompact
    ? { top: 34, right: 48, bottom: 48, left: 48 }
    : { top: 38, right: 76, bottom: 56, left: 64 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const minTime = visibleRows[0].date.getTime();
  const maxTime = visibleRows.at(-1).date.getTime();
  const yieldValues = visibleRows.map((row) => row.yieldPct);
  const priceValues = visibleRows.map((row) => row.close);
  const yieldRange = paddedRange(yieldValues);
  const priceRange = paddedRange(priceValues);
  const minYield = Math.floor(yieldRange.min * 10) / 10;
  const maxYield = Math.ceil(yieldRange.max * 10) / 10;
  const minPrice = priceRange.min;
  const maxPrice = priceRange.max;
  const xScale = (date) => margin.left + ((date.getTime() - minTime) / (maxTime - minTime || 1)) * plotWidth;
  const yieldScale = (value) => margin.top + ((maxYield - value) / (maxYield - minYield)) * plotHeight;
  const priceScale = (value) => margin.top + ((maxPrice - value) / (maxPrice - minPrice)) * plotHeight;
  const yieldPoints = visibleRows.map((row) => ({ x: xScale(row.date), y: yieldScale(row.yieldPct) }));
  const pricePoints = visibleRows.map((row) => ({ x: xScale(row.date), y: priceScale(row.close) }));

  chart.textContent = "";
  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("width", "100%");
  chart.setAttribute("height", String(height));

  const grid = makeSvgElement("g", { class: "chart-grid" });
  const axis = makeSvgElement("g", { class: "chart-axis" });
  const yTicks = isPhone ? 4 : 5;
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
      x: margin.left - (isPhone ? 8 : 10),
      y: y + 4,
      "text-anchor": "end",
    });
    label.textContent = `${yieldValue.toFixed(1)}%`;
    axis.appendChild(label);

    const priceLabel = makeSvgElement("text", {
      class: "price-axis",
      x: width - margin.right + (isPhone ? 6 : 10),
      y: y + 4,
      "text-anchor": "start",
    });
    priceLabel.textContent = priceValue.toFixed(activeFund.decimals === 3 ? 2 : 1);
    axis.appendChild(priceLabel);
  }

  const seenMonths = new Set();
  const shortRange = maxTime - minTime < 93 * 86400000;
  const monthTicks = shortRange ? visibleRows : visibleRows.filter((row) => {
    const month = row.tradeDate.slice(0, 7);
    if (seenMonths.has(month)) return false;
    seenMonths.add(month);
    return true;
  });
  const stride = Math.max(1, Math.ceil(monthTicks.length / (isPhone ? 4 : isCompact ? 6 : 10)));
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
    label.textContent = shortRange ? row.tradeDate.slice(5) : isPhone ? row.tradeDate.slice(2, 7) : row.tradeDate.slice(0, 7);
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
  priceLegend.textContent = `收盘价 (${activeFund.currency})`;
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
    selectDate(viewStart + getNearestIndex(svgX, yieldPoints));
  });
  chart.appendChild(overlay);

  const hitLayer = makeSvgElement("g", { class: "hit-layer" });
  yieldPoints.forEach((point, index) => {
    const hit = makeSvgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: isPhone ? 11 : 7,
      tabindex: 0,
      role: "button",
      "aria-label": `${visibleRows[index].tradeDate} ${formatPercent(visibleRows[index].yieldPct)} ${formatCurrency(visibleRows[index].close)}`,
    });
    hit.addEventListener("click", () => {
      selectDate(viewStart + index);
    });
    hit.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectDate(viewStart + index);
      }
    });
    hitLayer.appendChild(hit);
  });
  chart.appendChild(hitLayer);

  const selected = yieldPoints[selectedIndex - viewStart];
  const selectedPrice = pricePoints[selectedIndex - viewStart];
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
    r: isPhone ? 7 : 6,
  }));
  chart.appendChild(makeSvgElement("circle", {
    class: "selected-price-point",
    cx: selectedPrice.x,
    cy: selectedPrice.y,
    r: isPhone ? 6 : 5,
  }));
}

const hkSourceNote = document.querySelector("#constituentSourceNote").innerHTML;

async function switchFund(id) {
  if (!FUNDS[id]) return;
  const token = ++loadToken;
  activeFundId = id;
  activeFund = FUNDS[id];
  const fund = activeFund;
  rows = [];
  selectedIndex = -1;
  viewStart = 0;
  viewEnd = -1;
  dateControls.disabled = true;
  document.querySelector("#yieldBasisNote").hidden = true;
  document.querySelector("#dateRangeLabel").textContent = "正在加载…";
  document.querySelector("#selectedDateLabel").value = "—";
  document.querySelector("#dateOverview").textContent = "";
  document.querySelector("#dateFirst").textContent = "—";
  document.querySelector("#dateLast").textContent = "—";
  chart.textContent = "";
  document.querySelectorAll("[data-latest-field], [data-field]").forEach((el) => { el.textContent = "—"; });
  document.querySelectorAll("[data-fund]").forEach((el) => el.setAttribute("aria-pressed", String(el.dataset.fund === id)));
  document.querySelectorAll("[data-dividend-label]").forEach((el) => { el.textContent = fund.dividendLabel; });
  document.querySelectorAll("[data-yield-label]").forEach((el) => { el.textContent = fund.yieldLabel; });
  document.querySelector("#fundTitle").textContent = fund.name;
  chart.setAttribute("aria-label", `${fund.name} 每日股息率与收盘价交互折线图`);
  document.querySelector("#calculationNote").textContent = fund.calculation;
  document.querySelector("#indexName").textContent = fund.index;
  document.querySelector("#companyInfoLabel").textContent = fund.currency === "CNY" ? "行业" : "主营业务";
  document.querySelector("#holdingWeightLabel").textContent = fund.currency === "CNY" ? "基金持仓（报告）" : "基金持仓";
  document.querySelector("[data-index-weight]").hidden = fund.currency !== "CNY";
  document.querySelector("#holdingsDateLabel").textContent = fund.currency === "CNY" ? "基金持仓报告日期" : "基金持仓日期";
  document.querySelector("#tableCaption").textContent = fund.currency === "CNY" ? "正在核对成分股与持仓报告…" : "按 03466 官网持股比例排序；公司名称和主营业务来自港交所官网。";
  document.querySelector("#constituentSourceNote").innerHTML = fund.currency === "CNY" ? "" : hkSourceNote;
  document.querySelector(".constituent-table").classList.toggle("cn-table", fund.currency === "CNY");
  const status = document.querySelector("#dataStatus");
  status.textContent = "正在加载数据…";
  status.classList.remove("is-warning");
  [dailyCsvLink, dividendCsvLink, constituentCsvLink].forEach((el) => { el.removeAttribute("href"); el.setAttribute("aria-disabled", "true"); });
  constituentTableBody.innerHTML = '<tr><td colspan="6">正在加载官网成分股…</td></tr>';
  [constituentUpdatedAt, holdingsAsOf, constituentSyncedAt].forEach((el) => { el.textContent = "—"; });
  constituentCount.textContent = `— / ${fund.count}`;
  constituentStatus.textContent = "正在核对官网";
  constituentChanges.textContent = "正在读取成分变更…";
  const url = new URL(window.location.href);
  url.searchParams.set("fund", id);
  history.replaceState(null, "", url);
  const constituentPromise = initConstituents(fund, token).then(() => {
    if (token === loadToken) constituentCsvLink.removeAttribute("aria-disabled");
  }).catch((error) => {
    if (token !== loadToken) return;
    console.error(error);
    constituentStatus.textContent = "成分股加载失败";
    constituentStatus.classList.add("is-warning");
    constituentTableBody.innerHTML = '<tr><td colspan="6">暂无可验证的成分股快照，请稍后重试。</td></tr>';
    constituentChanges.textContent = "成分变更暂不可用";
  });
  try {
    const { csv, source, summary } = await fetchFirstAvailableCsv(fund);
    if (token !== loadToken) return;
    rows = parseCsv(csv).map((row) => ({
      tradeDate: row.trade_date, date: new Date(`${row.trade_date}T00:00:00+08:00`),
      close: toNumber(row.close), annualizedDividend: toNumber(row[fund.dividendField]), yieldPct: toNumber(row[fund.yieldField]),
      dividendCount: toNumber(row.actual_dividend_count), dividendFrequency: toNumber(row.annual_dividend_frequency),
      estimatedDividendCount: toNumber(row.estimated_dividend_count), dividendAsOf: row.dividend_as_of,
    })).filter((row) => row.close !== null && row.annualizedDividend !== null && row.yieldPct !== null);
    if (!rows.length) throw new Error("No valid dividend yield rows");
    dailyCsvLink.href = source.daily;
    dividendCsvLink.href = source.dividends;
    [dailyCsvLink, dividendCsvLink].forEach((el) => el.removeAttribute("aria-disabled"));
    selectedIndex = rows.length - 1;
    initDateControls();
    updateLatestMetrics(rows[selectedIndex]);
    updateReadout(rows[selectedIndex]);
    renderChart();
    const isRelease = source.daily.includes("/assets/");
    const temporary = summary.temporary_price_source ? "；未复权行情暂用腾讯日线，待 Data_Server 补齐后切回" : "；行情来自 Data_Server";
    status.textContent = `${isRelease ? "使用发布快照；" : ""}数据生成：${formatSyncedTime(summary.updated_at)}；交易日 ${summary.latest.trade_date}${temporary}。`;
    status.classList.toggle("is-warning", isRelease);
  } catch (error) {
    if (token !== loadToken) return;
    console.error(error);
    status.textContent = "行情或分红加载失败，请稍后重试。";
    status.classList.add("is-warning");
  }
  await constituentPromise;
}

document.querySelectorAll("[data-fund]").forEach((button) => {
  button.addEventListener("click", () => switchFund(button.dataset.fund));
});
window.addEventListener("resize", renderChart);
const requestedFund = new URLSearchParams(window.location.search).get("fund");
switchFund(FUNDS[requestedFund] ? requestedFund : "03466");

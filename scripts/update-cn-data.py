#!/usr/bin/env python3
"""515080 display snapshots; temporary sources are tied to an open data request."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from bisect import bisect_right
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd

SPEC = importlib.util.spec_from_file_location("hk_update", Path(__file__).with_name("update-data.py"))
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
SYMBOL = "515080"
LISTING_DATE = date(2019, 12, 27)
REQUEST_ID = "522b0258-c618-4ba0-b6e2-4a411d0f5d35"
CMF_URL = "https://static.cmfchina.com/web/fundDetail/515080/index.html"
CSI_URL = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000922cons.xls"
CSI_WEIGHT_URL = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/000922closeweight.xls"
TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
DAILY_NAME = "515080_ttm_dividend_yield_daily.csv"
CALCULATION_METHOD = "trading_day_allocated_ttm_v1"
PRICE_DISPLAY_METHOD = "cash_dividend_forward_v1"
DAILY_FIELDS = ["trade_date", "close", "source_id", "qfq_close", "qfq_cash_adjustment_cny", "daily_dividend_cny",
                "allocation_status", "allocation_period_start", "allocation_period_end",
                "allocation_trading_days", "allocation_source_ex_date",
                "ttm_window_start_exclusive", "ttm_trading_days", "ttm_history_complete",
                "ttm_estimated_trading_days", "ttm_estimated_dividend_cny",
                "ttm_dividend_cny", "ttm_dividend_yield_pct", "actual_365d_dividend_count",
                "actual_365d_dividend_cny", "actual_365d_dividend_yield_pct"]


def api(path, **params):
    return base.fetch_json(base.DATA_SERVER_API_BASE + path,
                           params={k: str(v) for k, v in params.items()},
                           headers={"X-Consumer-Id": base.DATA_SERVER_CONSUMER_ID})


def completed_day():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.date() if now.hour >= 18 else now.date() - timedelta(days=1)


def normalize_prices(rows):
    by_date = {}
    for row in rows:
        day = base.parse_date(str(row["trade_date"]))
        close = float(row["close"])
        if day < LISTING_DATE or not math.isfinite(close) or close <= 0:
            raise RuntimeError("Invalid 515080 unadjusted close")
        key = day.isoformat()
        if key in by_date and abs(float(by_date[key]["close"]) - close) > 1e-8:
            raise RuntimeError(f"Conflicting 515080 closes for {key}")
        by_date.setdefault(key, {**row, "trade_date": key, "close": close})
    return [by_date[key] for key in sorted(by_date)]


def price_window(start, end):
    payload = api("/v1/cn-equity-quotes", symbol=SYMBOL, market="SH", adjustment="raw",
                  **{"from": start.isoformat(), "to": end.isoformat(), "limit": 1000})
    rows = payload.get("items", [])
    if len(rows) >= 1000:
        if start == end:
            raise RuntimeError("515080 single-day result reached limit")
        middle = start + (end - start) // 2
        return price_window(start, middle) + price_window(middle + timedelta(days=1), end)
    for row in rows:
        if row.get("adjustment") != "raw" or row.get("symbol") != SYMBOL or row.get("market") != "SH":
            raise RuntimeError("Data_Server returned wrong 515080 quote identity/adjustment")
        if not start <= base.parse_date(row["trade_date"]) <= end:
            raise RuntimeError("515080 quote outside requested window")
    return rows


def temporary_prices(end):
    """Explicit raw `day` field only; never use qfqday or infer prices from NAV."""
    rows = []
    for year in range(LISTING_DATE.year, end.year + 1):
        start = max(LISTING_DATE, date(year, 1, 1))
        until = min(end, date(year, 12, 31))
        payload = base.fetch_json(TENCENT_URL, params={
            "param": f"sh515080,day,{start.isoformat()},{until.isoformat()},1000,",
        })
        if payload.get("code") != 0:
            raise RuntimeError("Tencent raw quote response failed")
        days = payload.get("data", {}).get("sh515080", {}).get("day")
        if not days or len(days) >= 1000:
            raise RuntimeError(f"Missing/truncated Tencent raw history for {year}")
        for item in days:
            d = base.parse_date(item[0])
            if not start <= d <= until:
                raise RuntimeError("Tencent raw date outside requested window")
            opening, close, high, low, volume = map(float, item[1:6])
            if not (0 < low <= min(opening, close) <= max(opening, close) <= high) or volume < 0:
                raise RuntimeError("Invalid Tencent raw OHLCV")
            rows.append({"trade_date": item[0], "close": close,
                         "source_id": "tencent_finance_raw_temporary", "source_url": TENCENT_URL})
        if year < end.year:
            time.sleep(10)
    return normalize_prices(rows)


def fetch_prices(end=None):
    end = end or completed_day()
    rows = []
    start = LISTING_DATE
    while start <= end:
        until = min(start + timedelta(days=89), end)
        rows.extend(price_window(start, until))
        start = until + timedelta(days=1)
    rows = normalize_prices(rows)  # conflicts must never trigger a fallback
    previous = base.read_csv_rows(base.OUTPUT_DIR / DAILY_NAME)
    if not previous:
        previous = base.read_csv_rows(base.ASSETS_DIR / DAILY_NAME)
    available = {r["trade_date"] for r in rows}
    previous_dates = {r["trade_date"] for r in previous}
    latest_expected = end
    while latest_expected.weekday() >= 5:
        latest_expected -= timedelta(days=1)
    complete = bool(rows) and rows[0]["trade_date"] == LISTING_DATE.isoformat()
    complete = complete and previous_dates <= available and rows[-1]["trade_date"] >= latest_expected.isoformat()
    if complete:
        return rows, False
    # Registration is persisted in project docs; do not silently use adjusted data.
    request = api(f"/v1/data-requests/{REQUEST_ID}")
    if request.get("status") not in {"submitted", "approved", "done"}:
        raise RuntimeError("515080 temporary source requires an active or completed data request")
    fallback = temporary_prices(end)
    merged = normalize_prices(rows + fallback)  # also compare every overlapping close
    if not merged or merged[0]["trade_date"] != LISTING_DATE.isoformat():
        raise RuntimeError("515080 history does not begin on the listing date")
    if not previous_dates <= {r["trade_date"] for r in merged}:
        raise RuntimeError("515080 history regressed; preserve previous snapshot")
    return merged, True


def fetch_dividends():
    payload = api("/v1/cn-etf-distributions", fund_code=SYMBOL, limit=1000)
    if payload.get("has_more") or not payload.get("items"):
        raise RuntimeError("Missing/truncated 515080 official distributions")
    rows = []
    for item in payload["items"]:
        amount = float(item["distribution_per_10_units"]) / 10
        ex_date = base.parse_date(item["ex_date"])
        if (item.get("fund_code") != SYMBOL or item.get("currency") != "CNY"
                or item.get("source_id") != "cmfchina" or ex_date < LISTING_DATE
                or not math.isfinite(amount) or amount <= 0):
            raise RuntimeError("Invalid 515080 official distribution")
        rows.append({"ex_date": ex_date, "record_date": item["record_date"],
                     "payment_date": item["payment_date"], "dividend_per_unit_cny": amount,
                     "distribution_per_10_units": item["distribution_per_10_units"],
                     "currency": "CNY", "source_url": item["source_url"]})
    if len({r["ex_date"] for r in rows}) != len(rows):
        raise RuntimeError("Duplicate 515080 ex-dividend date")
    return sorted(rows, key=lambda r: r["ex_date"])


def previous_year(day):
    """Twelve calendar months, including the leap-day boundary convention."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def calculate(prices, dividends):
    prices = normalize_prices(prices)
    if not prices or prices[0]["trade_date"] != LISTING_DATE.isoformat():
        raise RuntimeError("Trading-day allocation requires complete history from listing")
    days = [base.parse_date(row["trade_date"]) for row in prices]
    # Historical allocation deliberately backfills completed intervals, but an
    # announced payment whose ex-date is after the snapshot is never allocated.
    dividends = sorted((r for r in dividends if r["ex_date"] <= days[-1]), key=lambda r: r["ex_date"])
    if not dividends:
        raise RuntimeError("Missing 515080 distributions for TTM calculation")
    if len({r["ex_date"] for r in dividends}) != len(dividends):
        raise RuntimeError("Duplicate 515080 ex-dividend date")
    positions = {day: i for i, day in enumerate(days)}
    allocations = []
    start = 0
    for dividend in dividends:
        ex_date = dividend["ex_date"]
        amount = dividend["dividend_per_unit_cny"]
        if ex_date not in positions or not math.isfinite(amount) or amount <= 0:
            raise RuntimeError("Missing ex-date quote or invalid dividend for trading-day allocation")
        end = positions[ex_date] + 1
        count = end - start
        daily = amount / count
        allocation = {"daily_dividend_cny": daily, "allocation_status": "historical",
                      "allocation_period_start": days[start].isoformat(),
                      "allocation_period_end": ex_date.isoformat(),
                      "allocation_trading_days": count, "allocation_source_ex_date": ex_date.isoformat()}
        allocations.extend(dict(allocation) for _ in range(count))
        start = end
    # The next payment is unknown: carry the most recently completed interval's
    # per-session amount, explicitly estimated until the next ex-date backfill.
    if start < len(days):
        allocation = {**allocations[-1], "allocation_status": "estimated",
                      "allocation_period_start": days[start].isoformat(),
                      "allocation_period_end": None, "allocation_trading_days": None}
        allocations.extend(dict(allocation) for _ in range(len(days) - start))

    output = []
    first = dividends[0]["ex_date"]
    for i, (price, allocation) in enumerate(zip(prices, allocations)):
        day = days[i]
        cutoff = previous_year(day)
        window = allocations[bisect_right(days, cutoff):i + 1]
        complete = cutoff >= days[0]
        estimated = [r for r in window if r["allocation_status"] == "estimated"]
        amount = round(math.fsum(r["daily_dividend_cny"] for r in window), 12) if complete else None
        actual = [r for r in dividends if day - timedelta(days=365) < r["ex_date"] <= day]
        actual_amount = round(math.fsum(r["dividend_per_unit_cny"] for r in actual), 10) if day >= first else None
        # Cash-distribution ETF: adjust only the display price to the snapshot's
        # share basis. Actual/estimated TTM allocations never enter this price.
        cash_adjustment = round(math.fsum(r["dividend_per_unit_cny"] for r in dividends if day < r["ex_date"]), 10)
        qfq_close = round(price["close"] - cash_adjustment, 10)
        if qfq_close <= 0:
            raise RuntimeError("Invalid cash-dividend forward price; review corporate actions")
        output.append({**price, **allocation,
                       "qfq_close": qfq_close, "qfq_cash_adjustment_cny": cash_adjustment,
                       "ttm_window_start_exclusive": cutoff.isoformat(),
                       "ttm_trading_days": len(window), "ttm_history_complete": complete,
                       "ttm_estimated_trading_days": len(estimated),
                       "ttm_estimated_dividend_cny": round(math.fsum(r["daily_dividend_cny"] for r in estimated), 12),
                       "ttm_dividend_cny": amount,
                       "ttm_dividend_yield_pct": amount / price["close"] * 100 if amount is not None else None,
                       "actual_365d_dividend_count": len(actual),
                       "actual_365d_dividend_cny": actual_amount,
                       "actual_365d_dividend_yield_pct": actual_amount / price["close"] * 100 if actual_amount is not None else None})
    return output


def update_yield(recalculate=False):
    prior = {}
    if recalculate:
        # Reuse published raw closes for a formula-only release; still refresh official distributions.
        prior = base.read_json(base.OUTPUT_DIR / "515080_summary.json", {})
        prices = base.read_csv_rows(base.OUTPUT_DIR / DAILY_NAME)
        if (not prices or not isinstance(prior.get("temporary_price_source"), bool)
                or prices[-1]["trade_date"] != prior.get("latest", {}).get("trade_date")
                or len(prices) != prior.get("price_rows")):
            raise RuntimeError("Cannot recalculate without a matching published 515080 snapshot")
        prices = normalize_prices([{k: r[k] for k in ("trade_date", "close", "source_id")} for r in prices])
        if prices[0]["trade_date"] != LISTING_DATE.isoformat():
            raise RuntimeError("Cannot recalculate truncated 515080 history")
        temporary = prior["temporary_price_source"]
    else:
        prices, temporary = fetch_prices()
    dividends = fetch_dividends()
    daily = calculate(prices, dividends)
    latest = daily[-1]
    if latest["ttm_dividend_yield_pct"] is None:
        raise RuntimeError("515080 latest yield unavailable")
    now = datetime.now(base.timezone.utc).isoformat()
    summary = {"symbol": SYMBOL, "currency": "CNY", "updated_at": now,
               "latest": latest, "price_rows": len(daily), "dividend_rows": len(dividends),
               "price_snapshot_updated_at": prior.get("price_snapshot_updated_at", prior.get("updated_at")) if recalculate else now,
               "price_source": "Tencent raw daily quotes (temporary)" if temporary else "Data_Server raw CN quotes",
               "temporary_price_source": temporary, "data_request_id": REQUEST_ID,
               "dividend_source": "Data_Server /v1/cn-etf-distributions; CMF official announcements",
               "price_display_method": PRICE_DISPLAY_METHOD,
               "qfq_anchor_date": prices[-1]["trade_date"],
               "qfq_calculation": "display only: raw close minus actual cash distributions with trade_date < ex_date <= snapshot date; no estimated dividends; raw close remains the yield denominator",
               "qfq_source": "derived from verified raw closes and CMF official cash distributions; not stale Data_Server qfq quotes",
               "qfq_data_request_id": "0189023c-9f00-400a-8d97-4a765d640705",
               "calculation_method": CALCULATION_METHOD,
               "calculation": "allocate each completed dividend equally over quoted trading days in (previous ex-date, ex-date], first interval starts on listing date; sum allocations in (trade_date minus 12 months, trade_date], then divide by raw close",
               "history_policy": "retrospective allocation; completed intervals backfill history, not point-in-time cash returns; TTM blank before one full year of listing history",
               "open_interval_policy": "estimate each trading day using the latest completed interval daily amount; replace estimates after the next ex-date",
               "allocation_as_of": prices[-1]["trade_date"],
               "actual_365d_calculation": "unadjusted cash sum in (trade_date-365 days, trade_date], retained separately for audit"}
    base.write_csv(base.OUTPUT_DIR / DAILY_NAME, daily, DAILY_FIELDS)
    base.write_csv(base.OUTPUT_DIR / "515080_dividends_source_cmf.csv", dividends,
                   ["ex_date", "record_date", "payment_date", "dividend_per_unit_cny", "distribution_per_10_units", "currency", "source_url"])
    base.atomic_write_text(base.OUTPUT_DIR / "515080_summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"updated 515080 {latest['trade_date']} close={latest['close']:.3f} yield={latest['ttm_dividend_yield_pct']:.2f}% rows={len(daily)}", flush=True)


def parse_csi(data, weighted=False):
    sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
    if sheet.nrows != 101 or sheet.ncols != (10 if weighted else 9):
        raise RuntimeError("CSI Dividend official file must contain exactly 100 constituents")
    rows = []
    dates = set()
    exchanges = {"上海证券交易所": "SH", "深圳证券交易所": "SZ", "北京证券交易所": "BJ"}
    for i in range(1, sheet.nrows):
        r = sheet.row_values(i)
        if str(r[1]) != "000922" or r[7] not in exchanges:
            raise RuntimeError("Unexpected CSI index/exchange")
        day = datetime.strptime(str(r[0]), "%Y%m%d").date().isoformat()
        dates.add(day)
        code = str(r[4]).zfill(6)
        if not code.isdigit() or len(code) != 6 or not r[5]:
            raise RuntimeError("Invalid CSI constituent identity")
        row = {"symbol": code, "full_symbol": code + "." + exchanges[r[7]],
               "company_name_zh": r[5], "name": r[6]}
        if weighted:
            row["index_weight_pct"] = float(r[9])
            if not 0 < row["index_weight_pct"] <= 100:
                raise RuntimeError("Invalid CSI index weight")
        rows.append(row)
    if len(dates) != 1 or len({r["symbol"] for r in rows}) != 100:
        raise RuntimeError("Duplicate CSI constituent or mixed snapshot dates")
    if weighted and abs(sum(r["index_weight_pct"] for r in rows) - 100) > 0.1:
        raise RuntimeError("CSI index weights do not sum to 100%")
    return dates.pop(), rows


def update_constituents():
    official_date, rows = parse_csi(base.fetch_bytes(CSI_URL))
    weight_date, weights = parse_csi(base.fetch_bytes(CSI_WEIGHT_URL), weighted=True)
    weights = {r["symbol"]: r for r in weights}
    disclosed = base.read_json(base.ASSETS_DIR / "515080_disclosed_holdings.json", {})
    holdings = {r["symbol"]: r for r in disclosed.get("items", [])}
    if len(holdings) != 100 or disclosed.get("fund_code") != SYMBOL:
        raise RuntimeError("Invalid 515080 verified report snapshot")
    profiles = api("/v1/cn-equity-securities", limit=10000).get("items", [])
    industry = {r["symbol"]: r.get("industry") or r.get("sector") or "" for r in profiles}
    for row in rows:
        symbol = row["symbol"]
        row["weight_pct"] = holdings.get(symbol, {}).get("weight_pct")
        row["index_weight_pct"] = weights.get(symbol, {}).get("index_weight_pct")
        row["industry_zh"] = industry.get(symbol, "")
        row["report_company_name"] = holdings.get(symbol, {}).get("name", "")
    rows.sort(key=lambda r: (-(r["weight_pct"] or 0), r["symbol"]))
    csv_path = base.OUTPUT_DIR / "515080_csi_dividend_constituents.csv"
    old = base.read_csv_rows(csv_path) or base.read_csv_rows(base.ASSETS_DIR / csv_path.name)
    previous_summary = base.read_json(base.OUTPUT_DIR / "515080_constituents_summary.json", {})
    if previous_summary.get("official_updated_at", "") > official_date:
        raise RuntimeError("CSI snapshot date regressed")
    added, removed = base.compare_constituents(old, rows) if old else ([], [])
    history_path = base.OUTPUT_DIR / "515080_constituent_changes.json"
    history = base.read_json(history_path, []) or base.read_json(base.ASSETS_DIR / history_path.name, [])
    now = datetime.now(base.timezone.utc).isoformat()
    if added or removed:
        history.append({"detected_at": now, "official_updated_at": official_date, "added": added, "removed": removed})
    summary = {"index_symbol": "000922", "index_name": "中证红利", "official_updated_at": official_date,
               "index_weights_as_of": weight_date, "constituent_count": len(rows), "expected_count": 100,
               "sync_status": "synced", "count_matches_official": True, "synced_at": now,
               "holdings_as_of": disclosed["holdings_as_of"], "holdings_source_url": disclosed["source_url"],
               "holdings_scope": "interim report section 7.3.1 index-investment holdings; not live portfolio",
               "holding_weight_total_pct": disclosed["holding_weight_total_pct"],
               "holdings_matched_count": sum(r["weight_pct"] is not None for r in rows),
               "source_url": CSI_URL, "index_weight_source_url": CSI_WEIGHT_URL,
               "industry_source": "Data_Server /v1/cn-equity-securities",
               "comparison_basis": "previous_snapshot" if old else "none", "added_since_previous": added,
               "removed_since_previous": removed, "latest_change": history[-1] if history else None,
               "data_request_id": REQUEST_ID}
    base.write_csv(csv_path, rows, ["symbol", "full_symbol", "company_name_zh", "name", "weight_pct", "index_weight_pct", "industry_zh", "report_company_name"])
    base.atomic_write_text(history_path, json.dumps(history[-50:], ensure_ascii=False, indent=2) + "\n")
    base.atomic_write_text(base.OUTPUT_DIR / "515080_constituents_summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"updated 515080 constituents={len(rows)} official_date={official_date} holdings_date={disclosed['holdings_as_of']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--constituents-only", action="store_true")
    mode.add_argument("--recalculate", action="store_true", help="recalculate published raw closes with current official dividends")
    args = parser.parse_args()
    base.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    update_constituents() if args.constituents_only else update_yield(recalculate=args.recalculate)

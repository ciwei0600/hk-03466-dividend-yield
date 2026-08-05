#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime-data"
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR = Path(os.environ.get("DATA_OUTPUT_DIR", str(RUNTIME_DIR)))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = PROJECT_ROOT / OUTPUT_DIR
DATA_SERVER_API_BASE = os.environ.get("DATA_SERVER_API_BASE", "http://100.77.62.83:8010").rstrip("/")
DATA_SERVER_CONSUMER_ID = os.environ.get("DATA_SERVER_CONSUMER_ID", "cash-ranking")
HSI_ETF_DETAIL_URL = (
    "https://rbwm-api.hsbc.com.hk/"
    "pws-hk-hase-hsvm2-papi-prod-proxy/v1/hsvm/aem/etffunddetail"
)
HSI_ETF_PAGE_URL = (
    "https://www.hangsenginvestment.com/en-hk/individual-investor/"
    "our-products/etf-listed-details/?FundClass=NA&FundUnit=NA&TrustNo=H0E329"
)
ETF_LISTED_HKD_FUND_CODE = "3466"
ETF_LISTING_DATE = date(2025, 4, 7)
HSI_INDEX_CODE = "hshd30"
HSI_INDEX_CONSTITUENTS_URL = (
    f"https://www.hsi.com.hk/data/eng/rt/index-series/{HSI_INDEX_CODE}/constituents.do"
)
HSI_INDEX_PAGE_URL = "https://www.hsi.com.hk/eng/indexes/all-indexes/hshd30"
HSI_HOLDINGS_URL = "https://cms.hangsenginvestment.com/cms/ivp/hsvm/listed/composition/H0E329.xml"
HKEX_QUOTE_API_URL = "https://www1.hkex.com.hk/hkexwidget/data/getequityquote"
HKEX_QUOTE_PAGE_URL = (
    "https://www.hkex.com.hk/Market-Data/Securities-Prices/Equities/Equities-Quote"
)
USER_AGENT = "hk-03466-dividend-yield/0.6.0"


def fetch_bytes(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    accept: str = "*/*",
) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        safe_url = re.sub(r"([?&]token=)[^&]+", r"\1[redacted]", url)
        raise RuntimeError(f"HTTP {exc.code} from {safe_url}: {body[:300]}") from exc


def fetch_text(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    accept: str = "text/plain,*/*",
) -> str:
    return fetch_bytes(url, params=params, headers=headers, accept=accept).decode("utf-8")


def fetch_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    return json.loads(
        fetch_text(url, params=params, headers=headers, accept="application/json")
    )


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def deduplicate_prices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        trade_date = str(row.get("trade_date") or "")[:10]
        if not trade_date or row.get("close") is None:
            raise RuntimeError("Data_Server returned a price row without trade_date or close")
        grouped.setdefault(trade_date, []).append(row)

    deduplicated = []
    for trade_date, candidates in grouped.items():
        close_values = {round(float(row["close"]), 8) for row in candidates}
        if len(close_values) != 1:
            sources = ", ".join(
                f"{row.get('source_id', 'unknown')}={row.get('close')}" for row in candidates
            )
            raise RuntimeError(f"Conflicting 03466 closes for {trade_date}: {sources}")

        preferred = [row for row in candidates if row.get("source_id") == "tencent_finance"]
        pool = preferred or candidates
        selected = max(
            pool,
            key=lambda row: (str(row.get("source_updated_at") or ""), str(row.get("ingested_at") or "")),
        )
        deduplicated.append(selected)

    deduplicated.sort(key=lambda row: row["trade_date"])
    return deduplicated


def fetch_prices() -> list[dict[str, Any]]:
    payload = fetch_json(
        f"{DATA_SERVER_API_BASE}/v1/hk-equity-quotes",
        params={
            "symbol": "03466",
            "from": "2025-04-07",
            "to": date.today().isoformat(),
            "limit": "1000",
        },
        headers={"X-Consumer-Id": DATA_SERVER_CONSUMER_ID},
    )
    rows = payload.get("items") or []
    if not rows:
        raise RuntimeError("Data_Server returned no 03466 price rows")
    return deduplicate_prices(rows)


def fetch_dividends() -> list[dict[str, Any]]:
    payload = fetch_json(
        HSI_ETF_DETAIL_URL,
        params={"trustNo": "H0E329"},
        headers={"Referer": HSI_ETF_PAGE_URL},
    )
    classes = payload.get("Fund", {}).get("FundUnitClass") or []
    if not isinstance(classes, list):
        classes = [classes]

    listed_hkd = next(
        (
            item
            for item in classes
            if str(item.get("Fund_code")) == ETF_LISTED_HKD_FUND_CODE
            and item.get("Class_curr_symbol") == "HKD"
        ),
        None,
    )
    if listed_hkd is None:
        raise RuntimeError("Hang Seng Investment payload has no listed HKD counter 3466 class")

    listing_date = parse_date(listed_hkd.get("Listing_date") or ETF_LISTING_DATE.isoformat())
    if listing_date != ETF_LISTING_DATE:
        raise RuntimeError(
            f"Unexpected 03466 listing date from Hang Seng Investment: {listing_date.isoformat()}"
        )

    dividends = listed_hkd.get("Dividends", {}).get("Dividend") or []
    if not isinstance(dividends, list):
        dividends = [dividends]
    if not dividends:
        raise RuntimeError("Hang Seng Investment returned no 03466 listed-class distributions")

    parsed = []
    for row in dividends:
        ex_date = parse_date(row["Ex_div_date"])
        currency = row["Currency"]
        amount = float(row["Div"])
        if ex_date < listing_date:
            raise RuntimeError(
                f"Hang Seng Investment listed class contains pre-listing distribution {ex_date.isoformat()}"
            )
        if currency != "HKD" or amount <= 0:
            raise RuntimeError(
                f"Invalid 03466 listed-class distribution on {ex_date.isoformat()}: {currency} {amount}"
            )
        parsed.append(
            {
                "ex_date": ex_date,
                "record_date": parse_date(row["Record_date"]),
                "payment_date": parse_date(row["Payment_date"]),
                "currency": currency,
                "dividend_per_unit_hkd": amount,
                "div_serial_no": row.get("Div_serial_no", ""),
            }
        )
    parsed.sort(key=lambda row: row["ex_date"])
    ex_dates = [row["ex_date"] for row in parsed]
    if len(ex_dates) != len(set(ex_dates)):
        raise RuntimeError("Hang Seng Investment listed class contains duplicate ex-dividend dates")
    return parsed


def fetch_index_constituents() -> tuple[dict[str, Any], list[dict[str, str]]]:
    payload = fetch_json(
        HSI_INDEX_CONSTITUENTS_URL,
        params={"_": str(int(datetime.now(timezone.utc).timestamp()))},
        headers={"Referer": HSI_INDEX_PAGE_URL},
    )
    series_list = payload.get("indexSeriesList") or []
    series = next(
        (item for item in series_list if str(item.get("seriesCode", "")).lower() == HSI_INDEX_CODE),
        None,
    )
    if series is None:
        raise RuntimeError("Hang Seng Indexes payload has no hshd30 series")

    index_list = series.get("indexList") or []
    index = next((item for item in index_list if item.get("constituentsCount") == 30), None)
    if index is None:
        raise RuntimeError("Hang Seng Indexes payload has no 30-constituent HSHD30 index")

    content = index.get("constituentContent") or []
    rows = [
        {
            "symbol": str(item["code"]).zfill(5),
            "name": str(item["constituentName"]).strip(),
            "share_type": str(item.get("type") or "").strip(),
        }
        for item in content
        if str(item.get("code") or "").strip() and str(item.get("constituentName") or "").strip()
    ]
    symbols = [row["symbol"] for row in rows]
    if len(rows) != 30 or len(set(symbols)) != 30:
        raise RuntimeError(
            f"Hang Seng Indexes HSHD30 validation failed: rows={len(rows)}, unique_symbols={len(set(symbols))}"
        )

    metadata = {
        "index_symbol": "HSHD30",
        "index_name": series.get("seriesName") or index.get("indexName") or "Hang Seng High Dividend 30 Index",
        "official_updated_at": series.get("constituentsDate"),
        "official_request_at": payload.get("requestDate"),
        "constituent_count": len(rows),
    }
    return metadata, rows


def parse_percentage(value: str | None, field_name: str) -> float:
    normalized = str(value or "").strip()
    if not normalized.endswith("%"):
        raise RuntimeError(f"Hang Seng Investment {field_name} is not a percentage: {normalized}")
    try:
        parsed = float(normalized[:-1].replace(",", ""))
    except ValueError as exc:
        raise RuntimeError(
            f"Hang Seng Investment {field_name} is not numeric: {normalized}"
        ) from exc
    if parsed < 0 or parsed > 100:
        raise RuntimeError(f"Hang Seng Investment {field_name} is out of range: {parsed}")
    return parsed


def xml_text(element: ET.Element, name: str) -> str:
    return str(element.findtext(name) or "").strip()


def parse_holdings_xml(payload: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RuntimeError("Hang Seng Investment portfolio composition XML is invalid") from exc
    if root.tag != "ETFS":
        raise RuntimeError(f"Unexpected Hang Seng Investment XML root: {root.tag}")

    try:
        declared_count = int(xml_text(root, "Number_of_Stocks").replace(",", ""))
    except ValueError as exc:
        raise RuntimeError("Hang Seng Investment portfolio has no valid stock count") from exc
    if declared_count != 30:
        raise RuntimeError(
            f"Hang Seng Investment portfolio declared stock count is {declared_count}, expected 30"
        )
    if xml_text(root, "Base_Currency") != "HKD":
        raise RuntimeError("Hang Seng Investment portfolio base currency is not HKD")
    if not xml_text(root, "Stock_Code").startswith("3466_"):
        raise RuntimeError("Hang Seng Investment portfolio is not the 03466 fund")

    rows: list[dict[str, Any]] = []
    for item in root.findall("ETF"):
        code_match = re.fullmatch(r"(\d{1,5})\s+HK", xml_text(item, "StockCode"))
        if code_match is None:
            raise RuntimeError(
                f"Hang Seng Investment portfolio has an invalid HK stock code: {xml_text(item, 'StockCode')}"
            )
        symbol = code_match.group(1).zfill(5)
        weight_pct = parse_percentage(xml_text(item, "Weight"), f"weight for {symbol}")
        if weight_pct <= 0:
            raise RuntimeError(f"Hang Seng Investment portfolio weight is not positive for {symbol}")
        name = xml_text(item, "StockName")
        if not name:
            raise RuntimeError(f"Hang Seng Investment portfolio has no name for {symbol}")
        rows.append(
            {
                "symbol": symbol,
                "full_symbol": f"{symbol}.HK",
                "fund_name": name,
                "fund_name_zh": xml_text(item, "StockName_ts") or name,
                "sector": xml_text(item, "Sector"),
                "sector_zh": xml_text(item, "Sector_ts") or xml_text(item, "Sector"),
                "weight_pct": weight_pct,
            }
        )

    symbols = [row["symbol"] for row in rows]
    if len(rows) != declared_count or len(set(symbols)) != declared_count:
        raise RuntimeError(
            "Hang Seng Investment portfolio validation failed: "
            f"rows={len(rows)}, unique_symbols={len(set(symbols))}"
        )
    stock_asset_pct = parse_percentage(xml_text(root, "Stock_Asset"), "stock asset")
    cash_equivalent_pct = parse_percentage(
        xml_text(root, "Cash_Equivalent_Asset"), "cash equivalent asset"
    )
    weight_total_pct = round(sum(row["weight_pct"] for row in rows), 2)
    if abs(weight_total_pct - stock_asset_pct) > 0.20:
        raise RuntimeError(
            "Hang Seng Investment portfolio weights do not reconcile: "
            f"rows={weight_total_pct:.2f}%, stock_asset={stock_asset_pct:.2f}%"
        )
    if abs(stock_asset_pct + cash_equivalent_pct - 100) > 0.05:
        raise RuntimeError(
            "Hang Seng Investment stock and cash allocation does not reconcile to 100%"
        )

    as_of_raw = xml_text(root, "As_of_date")
    try:
        as_of = datetime.strptime(as_of_raw, "%d %b %Y").date().isoformat()
    except ValueError as exc:
        raise RuntimeError(
            f"Hang Seng Investment portfolio has an invalid as-of date: {as_of_raw}"
        ) from exc
    metadata = {
        "holdings_as_of": as_of,
        "holdings_count": len(rows),
        "stock_asset_pct": stock_asset_pct,
        "cash_equivalent_pct": cash_equivalent_pct,
        "holding_weight_total_pct": weight_total_pct,
    }
    return metadata, rows


def fetch_fund_holdings() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = fetch_bytes(
        HSI_HOLDINGS_URL,
        headers={"Referer": HSI_ETF_PAGE_URL},
        accept="application/xml,text/xml,*/*",
    )
    return parse_holdings_xml(payload)


def clean_profile_text(value: str | None) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def summarize_business(summary: str) -> str:
    first_sentence = re.split(r"(?<=[。！？])", summary, maxsplit=1)[0].strip()
    if not first_sentence:
        raise RuntimeError("HKEX company profile has no usable business summary")
    if len(first_sentence) > 120:
        return first_sentence[:119].rstrip("，,；; ") + "…"
    return first_sentence


def parse_hkex_profile(payload: str, expected_symbol: str) -> dict[str, str]:
    match = re.fullmatch(r"\s*[^()]+\((.*)\)\s*;?\s*", payload, flags=re.DOTALL)
    if match is None:
        raise RuntimeError(f"HKEX returned invalid profile JSONP for {expected_symbol}")
    try:
        result = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"HKEX returned invalid profile JSON for {expected_symbol}") from exc
    data = result.get("data") or {}
    quote = data.get("quote") or {}
    if str(data.get("responsecode")) != "000" or quote.get("product_type") != "EQTY":
        raise RuntimeError(f"HKEX returned no equity profile for {expected_symbol}")
    actual_symbol = str(quote.get("sym") or "").zfill(5)
    if actual_symbol != expected_symbol:
        raise RuntimeError(
            f"HKEX profile symbol mismatch: expected {expected_symbol}, got {actual_symbol}"
        )
    company_name_zh = clean_profile_text(
        quote.get("nm_s") or quote.get("nm") or quote.get("issuer_name")
    )
    full_summary = clean_profile_text(quote.get("summary"))
    if not company_name_zh or not full_summary:
        raise RuntimeError(f"HKEX profile is missing company name or summary for {expected_symbol}")
    return {
        "company_name_zh": company_name_zh,
        "business_summary": summarize_business(full_summary),
        "industry_zh": clean_profile_text(
            quote.get("hsic_sub_sector_classification")
            or quote.get("hsic_ind_classification")
        ),
        "profile_updated_at": clean_profile_text(quote.get("db_updatetime")),
    }


def fetch_hkex_access_token() -> str:
    page = fetch_text(
        HKEX_QUOTE_PAGE_URL,
        params={"sc_lang": "zh-CN", "sym": "371"},
        accept="text/html,application/xhtml+xml",
    )
    function_match = re.search(
        r"LabCI\.getToken\s*=\s*function\s*\(\)\s*\{(.*?)\};",
        page,
        flags=re.DOTALL,
    )
    if function_match is None:
        raise RuntimeError("HKEX quote page has no public widget access-token function")
    tokens = re.findall(
        r"^[ \t]*return\s+[\"']([^\"']+)[\"']\s*;",
        function_match.group(1),
        flags=re.MULTILINE,
    )
    if not tokens:
        raise RuntimeError("HKEX quote page has no public widget access token")
    return tokens[0]


def fetch_hkex_profile(symbol: str, token: str) -> dict[str, str]:
    callback = "hkexProfileCallback"
    payload = fetch_text(
        HKEX_QUOTE_API_URL,
        params={
            "sym": str(int(symbol)),
            "lang": "chn",
            "token": token,
            "qid": symbol,
            "callback": callback,
        },
        headers={
            "Referer": f"{HKEX_QUOTE_PAGE_URL}?sc_lang=zh-CN&sym={int(symbol)}",
            "Origin": "https://www.hkex.com.hk",
        },
        accept="application/javascript,application/json,*/*",
    )
    return parse_hkex_profile(payload, symbol)


def fetch_constituents() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_metadata, index_rows = fetch_index_constituents()
    holdings_metadata, holdings = fetch_fund_holdings()
    index_by_symbol = {row["symbol"]: row for row in index_rows}
    holding_symbols = {row["symbol"] for row in holdings}
    index_symbols = set(index_by_symbol)
    if holding_symbols != index_symbols:
        missing_from_holdings = sorted(index_symbols - holding_symbols)
        missing_from_index = sorted(holding_symbols - index_symbols)
        raise RuntimeError(
            "Official constituent and 03466 portfolio symbols do not match: "
            f"missing_from_holdings={missing_from_holdings}, missing_from_index={missing_from_index}"
        )

    token = fetch_hkex_access_token()
    merged: list[dict[str, Any]] = []
    for holding in holdings:
        index_row = index_by_symbol[holding["symbol"]]
        profile = fetch_hkex_profile(holding["symbol"], token)
        merged.append({**index_row, **holding, **profile})
    merged.sort(key=lambda row: (-row["weight_pct"], row["symbol"]))

    metadata = {
        **index_metadata,
        **holdings_metadata,
        "profiles_count": len(merged),
        "holdings_match_constituents": True,
    }
    return metadata, merged


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def compare_constituents(
    previous: list[dict[str, str]], current: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    previous_by_symbol = {row["symbol"]: row for row in previous}
    current_by_symbol = {row["symbol"]: row for row in current}
    added = [current_by_symbol[symbol] for symbol in current_by_symbol.keys() - previous_by_symbol.keys()]
    removed = [previous_by_symbol[symbol] for symbol in previous_by_symbol.keys() - current_by_symbol.keys()]
    added.sort(key=lambda row: row["symbol"])
    removed.sort(key=lambda row: row["symbol"])
    return added, removed


def calculate(prices: list[dict[str, Any]], dividends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for price in prices:
        trade_date = parse_date(price["trade_date"])
        close = float(price["close"])
        available = [row for row in dividends if row["ex_date"] <= trade_date][-12:]
        actual_count = len(available)
        actual_sum = round(sum(row["dividend_per_unit_hkd"] for row in available), 10)
        latest_monthly = available[-1]["dividend_per_unit_hkd"] if available else None
        if latest_monthly is None:
            annualized = None
            dividend_yield = None
        else:
            annualized = round(actual_sum + latest_monthly * max(0, 12 - actual_count), 10)
            dividend_yield = annualized / close

        output.append(
            {
                "trade_date": trade_date.isoformat(),
                "close": close,
                "source_id": price.get("source_id", ""),
                "actual_dividend_count": actual_count,
                "actual_dividend_sum_hkd": actual_sum,
                "latest_monthly_dividend_hkd": latest_monthly,
                "annualized_dividend_hkd": annualized,
                "annualized_dividend_yield": dividend_yield,
                "annualized_dividend_yield_pct": dividend_yield * 100 if dividend_yield is not None else None,
            }
        )
    return output


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        temp_name = tmp.name
    Path(temp_name).replace(path)
    path.chmod(0o644)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fieldnames})
        temp_name = tmp.name
    Path(temp_name).replace(path)
    path.chmod(0o644)


def write_constituent_snapshot(
    constituent_metadata: dict[str, Any], constituents: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    constituent_fields = [
        "symbol",
        "full_symbol",
        "company_name_zh",
        "name",
        "share_type",
        "weight_pct",
        "fund_name",
        "fund_name_zh",
        "sector",
        "sector_zh",
        "industry_zh",
        "business_summary",
        "profile_updated_at",
    ]
    constituent_path = OUTPUT_DIR / "03466_hshd30_constituents_hsi.csv"
    previous_constituents = read_csv_rows(constituent_path)
    comparison_basis = "previous_snapshot"
    if not previous_constituents and OUTPUT_DIR != ASSETS_DIR:
        previous_constituents = read_csv_rows(ASSETS_DIR / constituent_path.name)
        comparison_basis = "release_snapshot" if previous_constituents else "none"
    elif not previous_constituents:
        comparison_basis = "none"

    if previous_constituents:
        added, removed = compare_constituents(previous_constituents, constituents)
    else:
        added, removed = [], []
    history_path = OUTPUT_DIR / "constituent_changes.json"
    history = read_json(history_path, [])
    if not history and OUTPUT_DIR != ASSETS_DIR:
        history = read_json(ASSETS_DIR / history_path.name, [])
    if previous_constituents and (added or removed):
        event = {
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "official_updated_at": constituent_metadata["official_updated_at"],
            "added": added,
            "removed": removed,
        }
        signature = (
            event["official_updated_at"],
            tuple(row["symbol"] for row in added),
            tuple(row["symbol"] for row in removed),
        )
        existing_signatures = {
            (
                item.get("official_updated_at"),
                tuple(row.get("symbol") for row in item.get("added", [])),
                tuple(row.get("symbol") for row in item.get("removed", [])),
            )
            for item in history
        }
        if signature not in existing_signatures:
            history.append(event)
    history = history[-50:]

    write_csv(constituent_path, constituents, constituent_fields)
    atomic_write_text(history_path, json.dumps(history, ensure_ascii=False, indent=2) + "\n")

    constituent_summary = {
        **constituent_metadata,
        "sync_status": "synced",
        "expected_count": 30,
        "count_matches_official": constituent_metadata["constituent_count"] == 30,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "comparison_basis": comparison_basis,
        "added_since_previous": added,
        "removed_since_previous": removed,
        "latest_change": history[-1] if history else None,
        "source_name": "Hang Seng Indexes official website",
        "source_url": HSI_INDEX_PAGE_URL,
        "source_data_url": HSI_INDEX_CONSTITUENTS_URL,
        "holdings_source_name": "Hang Seng Investment official 03466 portfolio composition",
        "holdings_source_url": HSI_ETF_PAGE_URL,
        "holdings_source_data_url": HSI_HOLDINGS_URL,
        "business_source_name": "HKEX official equity quote company profile",
        "business_source_url_template": f"{HKEX_QUOTE_PAGE_URL}?sc_lang=zh-CN&sym={{symbol}}",
        "business_source_note": "Company profile text displayed by HKEX; profile provider: LSEG Data & Analytics",
    }
    atomic_write_text(
        OUTPUT_DIR / "constituents_summary.json",
        json.dumps(constituent_summary, ensure_ascii=False, indent=2) + "\n",
    )
    return added, removed


def update_yield_snapshot() -> None:
    prices = fetch_prices()
    dividends = fetch_dividends()
    daily = calculate(prices, dividends)

    daily_fields = [
        "trade_date",
        "close",
        "source_id",
        "actual_dividend_count",
        "actual_dividend_sum_hkd",
        "latest_monthly_dividend_hkd",
        "annualized_dividend_hkd",
        "annualized_dividend_yield",
        "annualized_dividend_yield_pct",
    ]
    dividend_fields = [
        "ex_date",
        "record_date",
        "payment_date",
        "currency",
        "dividend_per_unit_hkd",
        "div_serial_no",
    ]
    write_csv(OUTPUT_DIR / "03466_ttm_dividend_yield_daily_annualized.csv", daily, daily_fields)
    write_csv(OUTPUT_DIR / "03466_dividends_source_hsi.csv", dividends, dividend_fields)

    latest = next(row for row in reversed(daily) if row["annualized_dividend_yield_pct"] is not None)
    summary = {
        "symbol": "03466",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest": latest,
        "price_rows": len(prices),
        "dividend_rows": len(dividends),
        "data_server_api_base": DATA_SERVER_API_BASE,
        "data_server_consumer_id": DATA_SERVER_CONSUMER_ID,
        "price_source": "Data_Server /v1/hk-equity-quotes, unique trade dates",
        "dividend_source": "Hang Seng Investment official listed HKD counter 3466",
        "dividend_source_url": HSI_ETF_PAGE_URL,
        "listing_date": ETF_LISTING_DATE.isoformat(),
    }
    atomic_write_text(OUTPUT_DIR / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(
        "updated",
        latest["trade_date"],
        f"close={latest['close']:.2f}",
        f"yield={latest['annualized_dividend_yield_pct']:.2f}%",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh 03466 dashboard data")
    parser.add_argument(
        "--constituents-only",
        action="store_true",
        help="refresh only the HSHD30 official constituent snapshot",
    )
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.constituents_only:
        metadata, constituents = fetch_constituents()
        added, removed = write_constituent_snapshot(metadata, constituents)
        print(
            "updated",
            "HSHD30",
            f"constituents={len(constituents)}",
            f"official_updated_at={metadata['official_updated_at']}",
            f"added={len(added)}",
            f"removed={len(removed)}",
        )
        return

    update_yield_snapshot()


if __name__ == "__main__":
    main()

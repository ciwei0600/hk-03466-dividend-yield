#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime-data"
DATA_SERVER_API_BASE = os.environ.get("DATA_SERVER_API_BASE", "http://100.77.62.83:8010").rstrip("/")
DATA_SERVER_CONSUMER_ID = os.environ.get("DATA_SERVER_CONSUMER_ID", "cash-ranking")
HSI_ETF_DETAIL_URL = (
    "https://rbwm-api.hsbc.com.hk/"
    "pws-hk-hase-hsvm2-papi-prod-proxy/v1/hsvm/aem/etffunddetail"
)


def fetch_json(url: str, *, params: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "hk-03466-dividend-yield/0.2",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:300]}") from exc


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


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
    rows = sorted(rows, key=lambda row: row["trade_date"])
    return rows


def fetch_dividends() -> list[dict[str, Any]]:
    payload = fetch_json(
        HSI_ETF_DETAIL_URL,
        params={"trustNo": "H0E329"},
        headers={
            "Referer": (
                "https://www.hangsenginvestment.com/en-hk/individual-investor/"
                "our-products/etf-listed-details/?FundClass=NA&FundUnit=NA&TrustNo=H0E329"
            )
        },
    )
    classes = payload.get("Fund", {}).get("FundUnitClass") or []
    if not isinstance(classes, list):
        classes = [classes]

    listed_hkd = next(
        (
            item
            for item in classes
            if str(item.get("Fund_code")) == "3466" and item.get("Class_curr_symbol") == "HKD"
        ),
        None,
    )
    if listed_hkd is None:
        raise RuntimeError("Hang Seng Investment payload has no listed HKD counter 3466 class")

    dividends = listed_hkd.get("Dividends", {}).get("Dividend") or []
    if not isinstance(dividends, list):
        dividends = [dividends]

    parsed = []
    for row in dividends:
        parsed.append(
            {
                "ex_date": parse_date(row["Ex_div_date"]),
                "record_date": parse_date(row["Record_date"]),
                "payment_date": parse_date(row["Payment_date"]),
                "currency": row["Currency"],
                "dividend_per_unit_hkd": float(row["Div"]),
                "div_serial_no": row.get("Div_serial_no", ""),
            }
        )
    parsed.sort(key=lambda row: row["ex_date"])
    return parsed


def calculate(prices: list[dict[str, Any]], dividends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for price in prices:
        trade_date = parse_date(price["trade_date"])
        close = float(price["close"])
        available = [row for row in dividends if row["ex_date"] <= trade_date][-12:]
        actual_count = len(available)
        actual_sum = sum(row["dividend_per_unit_hkd"] for row in available)
        latest_monthly = available[-1]["dividend_per_unit_hkd"] if available else None
        if latest_monthly is None:
            annualized = None
            dividend_yield = None
        else:
            annualized = actual_sum + latest_monthly * max(0, 12 - actual_count)
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
        writer = csv.DictWriter(tmp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fieldnames})
        temp_name = tmp.name
    Path(temp_name).replace(path)
    path.chmod(0o644)


def main() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
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
    write_csv(RUNTIME_DIR / "03466_ttm_dividend_yield_daily_annualized.csv", daily, daily_fields)
    write_csv(RUNTIME_DIR / "03466_dividends_source_hsi.csv", dividends, dividend_fields)

    latest = next(row for row in reversed(daily) if row["annualized_dividend_yield_pct"] is not None)
    summary = {
        "symbol": "03466",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest": latest,
        "price_rows": len(prices),
        "dividend_rows": len(dividends),
        "data_server_api_base": DATA_SERVER_API_BASE,
        "data_server_consumer_id": DATA_SERVER_CONSUMER_ID,
    }
    atomic_write_text(RUNTIME_DIR / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(
        "updated",
        latest["trade_date"],
        f"close={latest['close']:.2f}",
        f"yield={latest['annualized_dividend_yield_pct']:.2f}%",
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
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
HSI_INDEX_CODE = "hshd30"
HSI_INDEX_CONSTITUENTS_URL = (
    f"https://www.hsi.com.hk/data/eng/rt/index-series/{HSI_INDEX_CODE}/constituents.do"
)
HSI_INDEX_PAGE_URL = "https://www.hsi.com.hk/eng/indexes/all-indexes/hshd30"


def fetch_json(url: str, *, params: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "hk-03466-dividend-yield/0.5.0",
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
        f"{DATA_SERVER_API_BASE}/v1/hk-etp-distributions",
        params={
            "symbol": "03466",
            "from": "2023-01-01",
            "to": date.today().isoformat(),
            "limit": "1000",
        },
        headers={"X-Consumer-Id": DATA_SERVER_CONSUMER_ID},
    )
    dividends = payload.get("items") or []
    if not dividends:
        raise RuntimeError("Data_Server returned no 03466 distribution rows")

    parsed = []
    for row in dividends:
        parsed.append(
            {
                "ex_date": parse_date(row["ex_date"]),
                "record_date": parse_date(row["record_date"]),
                "payment_date": parse_date(row["payment_date"]),
                "currency": row["currency"],
                "dividend_per_unit_hkd": float(row["distribution_per_unit"]),
                "div_serial_no": (row.get("attributes") or {}).get("div_serial_no", ""),
            }
        )
    parsed.sort(key=lambda row: row["ex_date"])
    return parsed


def fetch_constituents() -> tuple[dict[str, Any], list[dict[str, str]]]:
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


def write_constituent_snapshot(
    constituent_metadata: dict[str, Any], constituents: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    constituent_fields = ["symbol", "name", "share_type"]
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

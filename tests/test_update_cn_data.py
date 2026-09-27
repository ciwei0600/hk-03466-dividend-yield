import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("cn_update", Path(__file__).resolve().parents[1] / "scripts/update-cn-data.py")
cn = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cn)


class DividendTests(unittest.TestCase):
    def test_per_ten_units_becomes_per_unit(self):
        record = {"fund_code": "515080", "currency": "CNY", "source_id": "cmfchina",
                  "ex_date": "2026-09-16", "record_date": "2026-09-15", "payment_date": "2026-09-21",
                  "distribution_per_10_units": 0.15, "source_url": "https://www.cmfchina.com/example"}
        with patch.object(cn, "api", return_value={"items": [record], "has_more": False}):
            self.assertEqual(cn.fetch_dividends()[0]["dividend_per_unit_cny"], 0.015)
        with patch.object(cn, "api", return_value={"items": [record, record]}):
            with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                cn.fetch_dividends()

    def official_dividends(self):
        return [{"ex_date": date.fromisoformat(r["ex_date"]),
                 "dividend_per_unit_cny": float(r["dividend_per_unit_cny"])}
                for r in cn.base.read_csv_rows(cn.base.ASSETS_DIR / "515080_dividends_source_cmf.csv")]

    def official_prices(self):
        return [{"trade_date": r["trade_date"], "close": float(r["close"]), "source_id": r["source_id"]}
                for r in cn.base.read_csv_rows(cn.base.ASSETS_DIR / cn.DAILY_NAME)]

    def test_allocation_uses_only_trading_rows_and_excludes_previous_ex_date(self):
        days = ["2019-12-27", "2019-12-30", "2019-12-31", "2020-01-02",
                "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"]
        prices = [{"trade_date": d, "close": 1} for d in days]
        dividends = [{"ex_date": date(2019, 12, 31), "dividend_per_unit_cny": 0.06},
                     {"ex_date": date(2020, 1, 7), "dividend_per_unit_cny": 0.12}]
        rows = cn.calculate(prices, dividends)
        self.assertEqual([r["daily_dividend_cny"] for r in rows], [0.02] * 3 + [0.03] * 5)
        self.assertEqual([r["allocation_trading_days"] for r in rows], [3] * 3 + [4] * 4 + [None])
        self.assertEqual(rows[3]["allocation_period_start"], "2020-01-02")
        self.assertEqual(rows[-1]["allocation_status"], "estimated")
        self.assertTrue(all(r["ttm_dividend_cny"] is None for r in rows))
        self.assertEqual(len(rows), len(days))

    def test_every_official_payment_is_conserved_without_overlap(self):
        rows = cn.calculate(self.official_prices(), self.official_dividends())
        for dividend in self.official_dividends():
            interval = [r for r in rows if r["allocation_status"] == "historical"
                        and r["allocation_source_ex_date"] == dividend["ex_date"].isoformat()]
            self.assertEqual(len(interval), interval[0]["allocation_trading_days"])
            self.assertAlmostEqual(sum(r["daily_dividend_cny"] for r in interval), dividend["dividend_per_unit_cny"], places=12)
            self.assertEqual(interval[-1]["trade_date"], dividend["ex_date"].isoformat())
            self.assertEqual(len({r["daily_dividend_cny"] for r in interval}), 1)
        self.assertEqual(rows[0]["trade_date"], "2019-12-27")
        self.assertIsNone(rows[0]["ttm_dividend_yield_pct"])
        self.assertTrue(rows[-1]["ttm_history_complete"])

    def test_ttm_is_twelve_month_allocations_not_fixed_session_count_or_cash_sum(self):
        rows = cn.calculate(self.official_prices(), self.official_dividends())
        indexed = {r["trade_date"]: r for r in rows}
        leap = indexed["2024-02-29"]
        self.assertEqual(leap["ttm_window_start_exclusive"], "2023-02-28")
        for day in ["2024-02-29", "2026-06-17", "2026-06-18", "2026-09-16"]:
            row = indexed[day]
            window = [r for r in rows if row["ttm_window_start_exclusive"] < r["trade_date"] <= day]
            self.assertAlmostEqual(row["ttm_dividend_cny"], sum(r["daily_dividend_cny"] for r in window), places=11)
            self.assertEqual(row["ttm_trading_days"], len(window))
            self.assertAlmostEqual(row["ttm_dividend_yield_pct"], row["ttm_dividend_cny"] / row["close"] * 100)
        self.assertEqual(indexed["2026-09-16"]["actual_365d_dividend_count"], 5)
        self.assertAlmostEqual(indexed["2026-09-16"]["actual_365d_dividend_cny"], 0.085)
        self.assertIsNone(indexed["2020-12-25"]["ttm_dividend_cny"])
        self.assertIsNotNone(indexed["2020-12-28"]["ttm_dividend_cny"])

    def test_dividend_is_not_booked_as_a_lump_on_ex_date(self):
        rows = cn.calculate(self.official_prices(), self.official_dividends())
        indexed = {r["trade_date"]: r for r in rows}
        for day, previous in [("2026-06-18", "2026-06-17"), ("2026-09-16", "2026-09-15")]:
            new, old = indexed[day], indexed[previous]
            expired = sum(r["daily_dividend_cny"] for r in rows
                          if old["ttm_window_start_exclusive"] < r["trade_date"] <= new["ttm_window_start_exclusive"])
            self.assertAlmostEqual(new["ttm_dividend_cny"] - old["ttm_dividend_cny"], new["daily_dividend_cny"] - expired, places=11)
            self.assertLess(abs(new["ttm_dividend_cny"] - old["ttm_dividend_cny"]), 0.001)

    def test_future_payment_waits_for_ex_date_then_replaces_estimates(self):
        prices, dividends = self.official_prices(), self.official_dividends()
        before_prices = [r for r in prices if r["trade_date"] < "2026-09-16"]
        before = cn.calculate(before_prices, dividends[:-1])
        self.assertEqual(before, cn.calculate(before_prices, dividends))
        after = cn.calculate([r for r in prices if r["trade_date"] <= "2026-09-16"], dividends)
        past = {r["trade_date"]: r for r in before}
        for row in after:
            if "2026-06-18" < row["trade_date"] <= "2026-09-15":
                self.assertEqual(past[row["trade_date"]]["allocation_status"], "estimated")
                self.assertEqual(row["allocation_status"], "historical")
                self.assertEqual(row["ttm_estimated_trading_days"], 0)
        self.assertEqual(after[-1]["ttm_estimated_trading_days"], 0)
        full = cn.calculate(prices, dividends)
        latest = full[-1]
        tail = [r for r in full if r["trade_date"] > "2026-09-16"]
        self.assertEqual(latest["ttm_estimated_trading_days"], len(tail))
        self.assertTrue(all(r["allocation_status"] == "estimated" for r in tail))
        self.assertAlmostEqual(latest["ttm_estimated_dividend_cny"], len(tail) * after[-1]["daily_dividend_cny"], places=11)

    def test_missing_ex_date_cannot_silently_change_allocation(self):
        prices = [r for r in self.official_prices() if r["trade_date"] != "2026-06-18"]
        with self.assertRaisesRegex(RuntimeError, "Missing ex-date"):
            cn.calculate(prices, self.official_dividends())
        with self.assertRaisesRegex(RuntimeError, "complete history"):
            cn.calculate(self.official_prices()[1:], self.official_dividends())

    def test_recalculation_keeps_prices_and_original_price_timestamp(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cn.base, "OUTPUT_DIR", Path(folder)):
            prices = self.official_prices()
            cn.base.write_csv(Path(folder) / cn.DAILY_NAME, prices, list(prices[0]))
            (Path(folder) / "515080_summary.json").write_text(json.dumps({
                "temporary_price_source": False, "latest": prices[-1], "price_rows": len(prices), "updated_at": "original"}))
            with patch.object(cn, "fetch_dividends", return_value=self.official_dividends()), patch.object(cn, "fetch_prices") as fetch:
                cn.update_yield(recalculate=True)
                fetch.assert_not_called()
            daily = cn.base.read_csv_rows(Path(folder) / cn.DAILY_NAME)
            summary = cn.base.read_json(Path(folder) / "515080_summary.json", {})
            self.assertEqual([float(r["close"]) for r in daily], [r["close"] for r in prices])
            self.assertEqual(summary["price_snapshot_updated_at"], "original")
            self.assertEqual(summary["calculation_method"], cn.CALCULATION_METHOD)
            self.assertGreater(float(daily[-1]["ttm_estimated_dividend_cny"]), 0)

    def test_recalculation_refuses_mismatched_snapshot_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cn.base, "OUTPUT_DIR", Path(folder)):
            path = Path(folder) / cn.DAILY_NAME
            path.write_text("last successful snapshot")
            with self.assertRaisesRegex(RuntimeError, "matching published"):
                cn.update_yield(recalculate=True)
            self.assertEqual(path.read_text(), "last successful snapshot")


class PriceTests(unittest.TestCase):
    def test_conflicting_sources_are_not_suppressed(self):
        with self.assertRaisesRegex(RuntimeError, "Conflicting 515080"):
            cn.normalize_prices([{"trade_date": "2026-09-23", "close": p} for p in [1.543, 1.553]])

    def test_adjusted_source_response_is_rejected(self):
        with patch.object(cn, "api", return_value={"items": [{"symbol": "515080", "market": "SH", "adjustment": "qfq"}]}):
            with self.assertRaisesRegex(RuntimeError, "identity/adjustment"):
                cn.price_window(date(2026, 9, 1), date(2026, 9, 23))

    def test_saturated_single_day_fails(self):
        with patch.object(cn, "api", return_value={"items": [{}] * 1000}):
            with self.assertRaisesRegex(RuntimeError, "single-day"):
                cn.price_window(date(2026, 9, 23), date(2026, 9, 23))

    def test_temporary_source_does_not_use_qfq(self):
        with patch.object(cn.base, "fetch_json", return_value={"code": 0, "data": {"sh515080": {"qfqday": [["2019-12-27", "1", "1", "1", "1", "1"]]}}}):
            with self.assertRaisesRegex(RuntimeError, "Missing/truncated"):
                cn.temporary_prices(date(2019, 12, 31))

    def test_failure_preserves_previous_published_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cn.base, "OUTPUT_DIR", Path(folder)):
            path = Path(folder) / cn.DAILY_NAME
            path.write_text("last successful snapshot")
            with patch.object(cn, "fetch_prices", side_effect=RuntimeError("conflict")):
                with self.assertRaises(RuntimeError):
                    cn.update_yield()
            self.assertEqual(path.read_text(), "last successful snapshot")


class IndexTests(unittest.TestCase):
    def test_duplicate_codes_rejected(self):
        class Sheet:
            nrows = 101
            ncols = 9
            def row_values(self, i):
                return ["20260923", "000922", "中证红利", "CSI Dividend", "601919", "中远海控", "COSCO", "上海证券交易所", "SSE"]
        class Book:
            def sheet_by_index(self, i):
                return Sheet()
        with patch.object(cn.xlrd, "open_workbook", return_value=Book()):
            with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                cn.parse_csi(b"mock")

    def test_beijing_exchange_uses_bj_suffix(self):
        class Sheet:
            nrows = 101
            ncols = 9
            def row_values(self, i):
                return ["20260923", "000922", "中证红利", "CSI Dividend", str(920000 + i), "公司", "Company", "北京证券交易所", "BSE"]
        class Book:
            def sheet_by_index(self, i):
                return Sheet()
        with patch.object(cn.xlrd, "open_workbook", return_value=Book()):
            day, rows = cn.parse_csi(b"mock")
            self.assertEqual(day, "2026-09-23")
            self.assertEqual(rows[0]["full_symbol"], "920001.BJ")


if __name__ == "__main__":
    unittest.main()

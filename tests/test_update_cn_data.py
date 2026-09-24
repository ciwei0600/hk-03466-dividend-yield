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

    def test_ttm_uses_last_four_ex_dates_and_excludes_future_dividends(self):
        dividends = [{"ex_date": date.fromisoformat(d), "dividend_per_unit_cny": v} for d, v in
                     [("2025-09-23", 0.5), ("2025-12-18", 0.02), ("2026-03-18", 0.015),
                      ("2026-06-18", 0.02), ("2026-09-16", 0.015), ("2026-12-18", 0.6)]]
        rows = cn.calculate([{"trade_date": "2026-09-23", "close": 1.543}], dividends)
        self.assertEqual(rows[0]["actual_dividend_count"], 4)
        self.assertEqual(rows[0]["ttm_dividend_cny"], 0.07)
        self.assertAlmostEqual(rows[0]["ttm_dividend_yield_pct"], 0.07 / 1.543 * 100)

    def test_first_annual_distribution_and_pre_distribution_blank(self):
        dividends = [{"ex_date": date(2020, 11, 30), "dividend_per_unit_cny": 0.06}]
        rows = cn.calculate([{"trade_date": d, "close": 1} for d in ["2020-11-27", "2020-11-30", "2021-06-17"]], dividends)
        self.assertIsNone(rows[0]["ttm_dividend_yield_pct"])
        self.assertEqual(rows[1]["ttm_dividend_yield_pct"], 6)
        self.assertEqual(rows[2]["ttm_dividend_yield_pct"], 6)
        self.assertEqual(rows[1]["annual_dividend_frequency"], 1)

    def official_dividends(self):
        return [{"ex_date": date.fromisoformat(r["ex_date"]),
                 "dividend_per_unit_cny": float(r["dividend_per_unit_cny"])}
                for r in cn.base.read_csv_rows(cn.base.ASSETS_DIR / "515080_dividends_source_cmf.csv")]

    def test_anniversary_drift_never_creates_three_or_five_quarters(self):
        days = ["2026-06-16", "2026-06-17", "2026-06-18", "2026-09-16", "2026-09-17"]
        rows = cn.calculate([{"trade_date": d, "close": 1.5} for d in days], self.official_dividends())
        self.assertEqual([r["ttm_dividend_cny"] for r in rows], [0.065, 0.065, 0.07, 0.07, 0.07])
        self.assertEqual([r["actual_dividend_count"] for r in rows], [4] * 5)
        self.assertEqual([r["actual_365d_dividend_count"] for r in rows], [4, 3, 4, 5, 4])
        self.assertEqual(rows[3]["actual_365d_dividend_cny"], 0.085)

    def test_semiannual_stage_excludes_earlier_full_year_payment(self):
        rows = cn.calculate([{"trade_date": d, "close": 1} for d in
                             ["2021-06-18", "2021-12-09", "2022-06-20"]], self.official_dividends())
        self.assertEqual([r["ttm_dividend_cny"] for r in rows], [0.06] * 3)
        self.assertEqual([r["estimated_dividend_count"] for r in rows], [1, 0, 0])
        self.assertEqual([r["annual_dividend_frequency"] for r in rows], [2] * 3)

    def test_quarterly_transition_excludes_semiannual_and_labels_estimates(self):
        rows = cn.calculate([{"trade_date": d, "close": 1} for d in
                             ["2024-03-28", "2024-07-01", "2024-09-20", "2024-12-02"]], self.official_dividends())
        self.assertEqual([r["ttm_dividend_cny"] for r in rows], [0.06, 0.075, 0.065, 0.07])
        self.assertEqual([r["estimated_dividend_count"] for r in rows], [3, 2, 1, 0])
        self.assertEqual([r["actual_dividend_count"] for r in rows], [1, 2, 3, 4])
        self.assertEqual([r["annual_dividend_frequency"] for r in rows], [4] * 4)

    def test_future_distributions_cannot_rewrite_history(self):
        before = [r for r in self.official_dividends() if r["ex_date"] <= date(2026, 6, 17)]
        price = [{"trade_date": "2026-06-17", "close": 1.537}]
        self.assertEqual(cn.calculate(price, before), cn.calculate(price, self.official_dividends()))

    def test_recalculation_keeps_prices_and_original_price_timestamp(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cn.base, "OUTPUT_DIR", Path(folder)):
            price = [{"trade_date": "2019-12-27", "close": 1.01, "source_id": "verified"},
                     {"trade_date": "2026-09-16", "close": 1.55, "source_id": "verified"}]
            cn.base.write_csv(Path(folder) / cn.DAILY_NAME, price, list(price[0]))
            (Path(folder) / "515080_summary.json").write_text(json.dumps({
                "temporary_price_source": False, "latest": price[-1], "price_rows": 2, "updated_at": "original"}))
            with patch.object(cn, "fetch_dividends", return_value=self.official_dividends()), patch.object(cn, "fetch_prices") as fetch:
                cn.update_yield(recalculate=True)
                fetch.assert_not_called()
            daily = cn.base.read_csv_rows(Path(folder) / cn.DAILY_NAME)
            summary = cn.base.read_json(Path(folder) / "515080_summary.json", {})
            self.assertEqual([float(r["close"]) for r in daily], [1.01, 1.55])
            self.assertEqual(summary["price_snapshot_updated_at"], "original")
            self.assertEqual(summary["calculation_method"], cn.CALCULATION_METHOD)
            self.assertEqual(float(daily[-1]["ttm_dividend_cny"]), 0.07)

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

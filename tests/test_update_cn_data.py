import importlib.util
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

    def test_ttm_uses_ex_dates_and_excludes_future_and_old_dividends(self):
        dividends = [{"ex_date": date.fromisoformat(d), "dividend_per_unit_cny": v} for d, v in
                     [("2025-09-23", 0.5), ("2025-12-18", 0.02), ("2026-03-18", 0.015),
                      ("2026-06-18", 0.02), ("2026-09-16", 0.015), ("2026-12-18", 0.6)]]
        rows = cn.calculate([{"trade_date": "2026-09-23", "close": 1.543}], dividends)
        self.assertEqual(rows[0]["actual_dividend_count"], 4)
        self.assertEqual(rows[0]["ttm_dividend_cny"], 0.07)
        self.assertAlmostEqual(rows[0]["ttm_dividend_yield_pct"], 0.07 / 1.543 * 100)

    def test_before_first_distribution_is_blank_and_no_dividend_year_is_zero(self):
        dividends = [{"ex_date": date(2020, 11, 30), "dividend_per_unit_cny": 0.06}]
        rows = cn.calculate([{"trade_date": d, "close": 1} for d in ["2020-11-27", "2020-11-30", "2021-11-30"]], dividends)
        self.assertIsNone(rows[0]["ttm_dividend_yield_pct"])
        self.assertEqual(rows[1]["ttm_dividend_yield_pct"], 6)
        self.assertEqual(rows[2]["ttm_dividend_yield_pct"], 0)


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

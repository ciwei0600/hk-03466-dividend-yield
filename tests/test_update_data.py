import importlib.util
import unittest
from datetime import date
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update-data.py"
SPEC = importlib.util.spec_from_file_location("update_data", SCRIPT_PATH)
update_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(update_data)


class ConstituentParsingTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "requestDate": "2026-08-05 11:17:07",
            "indexSeriesList": [
                {
                    "seriesName": "Hang Seng High Dividend 30 Index",
                    "seriesCode": "hshd30",
                    "constituentsDate": "2026-08-05 07:32:54",
                    "indexList": [
                        {
                            "indexName": "Hang Seng High Dividend 30 Index",
                            "constituentsCount": 30,
                            "constituentContent": [
                                {
                                    "code": str(index),
                                    "constituentName": f"Company {index}",
                                    "type": "O",
                                }
                                for index in range(1, 31)
                            ],
                        }
                    ],
                }
            ],
        }

    def test_fetch_constituents_normalizes_and_validates_official_payload(self):
        original = update_data.fetch_json
        update_data.fetch_json = lambda *args, **kwargs: self.payload
        try:
            metadata, rows = update_data.fetch_constituents()
        finally:
            update_data.fetch_json = original

        self.assertEqual(metadata["index_symbol"], "HSHD30")
        self.assertEqual(metadata["official_updated_at"], "2026-08-05 07:32:54")
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["symbol"], "00001")

    def test_fetch_constituents_rejects_duplicate_symbols(self):
        self.payload["indexSeriesList"][0]["indexList"][0]["constituentContent"][1]["code"] = "1"
        original = update_data.fetch_json
        update_data.fetch_json = lambda *args, **kwargs: self.payload
        try:
            with self.assertRaisesRegex(RuntimeError, "validation failed"):
                update_data.fetch_constituents()
        finally:
            update_data.fetch_json = original

    def test_compare_constituents_reports_additions_and_removals(self):
        previous = [
            {"symbol": "00001", "name": "One", "share_type": "O"},
            {"symbol": "00002", "name": "Two", "share_type": "O"},
        ]
        current = [
            {"symbol": "00002", "name": "Two", "share_type": "O"},
            {"symbol": "00003", "name": "Three", "share_type": "H"},
        ]
        added, removed = update_data.compare_constituents(previous, current)
        self.assertEqual([row["symbol"] for row in added], ["00003"])
        self.assertEqual([row["symbol"] for row in removed], ["00001"])


class PriceNormalizationTests(unittest.TestCase):
    def test_deduplicate_prices_keeps_one_row_per_date_and_prefers_tencent(self):
        rows = [
            {
                "trade_date": "2026-07-29",
                "close": 20.48,
                "source_id": "yahoo_finance",
                "source_updated_at": "2026-07-29T09:00:00Z",
            },
            {
                "trade_date": "2026-07-29",
                "close": 20.48,
                "source_id": "tencent_finance",
                "source_updated_at": "2026-07-29T08:00:00Z",
            },
            {
                "trade_date": "2026-07-30",
                "close": 20.64,
                "source_id": "yahoo_finance",
                "source_updated_at": "2026-07-30T08:00:00Z",
            },
        ]
        result = update_data.deduplicate_prices(rows)
        self.assertEqual([row["trade_date"] for row in result], ["2026-07-29", "2026-07-30"])
        self.assertEqual(result[0]["source_id"], "tencent_finance")

    def test_deduplicate_prices_rejects_conflicting_closes(self):
        rows = [
            {"trade_date": "2026-07-29", "close": 20.48, "source_id": "yahoo_finance"},
            {"trade_date": "2026-07-29", "close": 20.50, "source_id": "tencent_finance"},
        ]
        with self.assertRaisesRegex(RuntimeError, "Conflicting 03466 closes"):
            update_data.deduplicate_prices(rows)


class DividendSourceTests(unittest.TestCase):
    def listed_class(self, dividends):
        return {
            "Fund_code": "3466",
            "Class_curr_symbol": "HKD",
            "Listing_date": "2025-04-07",
            "Dividends": {"Dividend": dividends},
        }

    def dividend(self, ex_date, amount):
        return {
            "Ex_div_date": f"{ex_date} 00:00:00.0",
            "Record_date": f"{ex_date} 00:00:00.0",
            "Payment_date": f"{ex_date} 00:00:00.0",
            "Currency": "HKD",
            "Div": str(amount),
            "Div_serial_no": "test",
        }

    def test_fetch_dividends_uses_only_official_listed_hkd_class(self):
        payload = {
            "Fund": {
                "FundUnitClass": [
                    {
                        "Fund_code": "U45624",
                        "Class_curr_symbol": "HKD",
                        "Listing_date": "",
                        "Dividends": {"Dividend": [self.dividend("2024-09-20", 0.5)]},
                    },
                    self.listed_class(
                        [self.dividend("2025-05-02", 0.09), self.dividend("2025-06-02", 0.10)]
                    ),
                ]
            }
        }
        original = update_data.fetch_json
        update_data.fetch_json = lambda *args, **kwargs: payload
        try:
            rows = update_data.fetch_dividends()
        finally:
            update_data.fetch_json = original

        self.assertEqual([row["ex_date"] for row in rows], [date(2025, 5, 2), date(2025, 6, 2)])
        self.assertEqual([row["dividend_per_unit_hkd"] for row in rows], [0.09, 0.10])

    def test_fetch_dividends_rejects_pre_listing_event_in_listed_class(self):
        payload = {
            "Fund": {
                "FundUnitClass": [self.listed_class([self.dividend("2024-09-20", 0.5)])]
            }
        }
        original = update_data.fetch_json
        update_data.fetch_json = lambda *args, **kwargs: payload
        try:
            with self.assertRaisesRegex(RuntimeError, "pre-listing distribution"):
                update_data.fetch_dividends()
        finally:
            update_data.fetch_json = original


class YieldRegressionTests(unittest.TestCase):
    def test_yield_is_blank_before_first_listed_distribution_and_latest_is_correct(self):
        prices = [
            {"trade_date": "2025-04-07", "close": 13.57, "source_id": "tencent_finance"},
            {"trade_date": "2025-05-02", "close": 14.74, "source_id": "tencent_finance"},
            {"trade_date": "2026-08-03", "close": 20.26, "source_id": "tencent_finance"},
        ]
        distributions = [
            ("2025-05-02", 0.09),
            ("2025-06-02", 0.10),
            ("2025-07-02", 0.10),
            ("2025-08-01", 0.11),
            ("2025-09-01", 0.12),
            ("2025-10-02", 0.12),
            ("2025-11-03", 0.12),
            ("2025-12-01", 0.13),
            ("2026-01-02", 0.13),
            ("2026-02-02", 0.13),
            ("2026-03-02", 0.13),
            ("2026-04-01", 0.13),
            ("2026-05-04", 0.13),
            ("2026-06-01", 0.13),
            ("2026-07-02", 0.11),
            ("2026-08-03", 0.11),
        ]
        dividends = [
            {"ex_date": date.fromisoformat(ex_date), "dividend_per_unit_hkd": amount}
            for ex_date, amount in distributions
        ]

        result = update_data.calculate(prices, dividends)
        self.assertIsNone(result[0]["annualized_dividend_yield_pct"])
        self.assertAlmostEqual(result[1]["annualized_dividend_hkd"], 1.08)
        self.assertAlmostEqual(result[1]["annualized_dividend_yield_pct"], 1.08 / 14.74 * 100)
        self.assertAlmostEqual(result[2]["annualized_dividend_hkd"], 1.49)
        self.assertAlmostEqual(result[2]["annualized_dividend_yield_pct"], 1.49 / 20.26 * 100)


if __name__ == "__main__":
    unittest.main()

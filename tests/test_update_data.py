import importlib.util
import json
import tempfile
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

    def test_fetch_index_constituents_normalizes_and_validates_official_payload(self):
        original = update_data.fetch_json
        update_data.fetch_json = lambda *args, **kwargs: self.payload
        try:
            metadata, rows = update_data.fetch_index_constituents()
        finally:
            update_data.fetch_json = original

        self.assertEqual(metadata["index_symbol"], "HSHD30")
        self.assertEqual(metadata["official_updated_at"], "2026-08-05 07:32:54")
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["symbol"], "00001")

    def test_fetch_index_constituents_rejects_duplicate_symbols(self):
        self.payload["indexSeriesList"][0]["indexList"][0]["constituentContent"][1]["code"] = "1"
        original = update_data.fetch_json
        update_data.fetch_json = lambda *args, **kwargs: self.payload
        try:
            with self.assertRaisesRegex(RuntimeError, "validation failed"):
                update_data.fetch_index_constituents()
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

    def test_latest_change_survives_a_later_no_change_sync(self):
        previous = [
            {"symbol": str(index).zfill(5), "name": f"Company {index}", "share_type": "O"}
            for index in range(1, 31)
        ]
        current = previous[1:] + [
            {"symbol": "00031", "name": "Company 31", "share_type": "O"}
        ]
        metadata = {
            "index_symbol": "HSHD30",
            "index_name": "Hang Seng High Dividend 30 Index",
            "official_updated_at": "2026-09-08 16:30:00",
            "official_request_at": "2026-09-08 16:31:00",
            "constituent_count": 30,
        }

        original_output_dir = update_data.OUTPUT_DIR
        original_assets_dir = update_data.ASSETS_DIR
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            runtime_dir = temporary_root / "runtime-data"
            assets_dir = temporary_root / "assets"
            runtime_dir.mkdir()
            assets_dir.mkdir()
            update_data.write_csv(
                assets_dir / "03466_hshd30_constituents_hsi.csv",
                previous,
                ["symbol", "name", "share_type"],
            )
            try:
                update_data.OUTPUT_DIR = runtime_dir
                update_data.ASSETS_DIR = assets_dir
                added, removed = update_data.write_constituent_snapshot(metadata, current)
                self.assertEqual([row["symbol"] for row in added], ["00031"])
                self.assertEqual([row["symbol"] for row in removed], ["00001"])

                first_summary = json.loads(
                    (runtime_dir / "constituents_summary.json").read_text(encoding="utf-8")
                )
                self.assertEqual(first_summary["latest_change"]["added"][0]["symbol"], "00031")

                later_metadata = {
                    **metadata,
                    "official_request_at": "2026-09-09 07:10:00",
                }
                added, removed = update_data.write_constituent_snapshot(later_metadata, current)
                self.assertEqual(added, [])
                self.assertEqual(removed, [])

                later_summary = json.loads(
                    (runtime_dir / "constituents_summary.json").read_text(encoding="utf-8")
                )
                self.assertEqual(later_summary["added_since_previous"], [])
                self.assertEqual(later_summary["removed_since_previous"], [])
                self.assertEqual(later_summary["latest_change"]["added"][0]["symbol"], "00031")
                self.assertEqual(later_summary["latest_change"]["removed"][0]["symbol"], "00001")
            finally:
                update_data.OUTPUT_DIR = original_output_dir
                update_data.ASSETS_DIR = original_assets_dir


class OfficialEnrichmentTests(unittest.TestCase):
    def holdings_xml(self, duplicate=False):
        rows = []
        for index in range(1, 31):
            code = 1 if duplicate and index == 2 else index
            rows.append(
                "<ETF>"
                f"<StockName>Company {index}</StockName>"
                f"<StockName_ts>公司 {index}</StockName_ts>"
                f"<StockCode>{code} HK</StockCode>"
                "<Sector>Industrials</Sector>"
                "<Sector_ts>工业</Sector_ts>"
                "<Exchange>Hong Kong</Exchange>"
                "<Weight>3.30%</Weight>"
                "</ETF>"
            )
        xml = (
            "<ETFS>"
            "<As_of_date>03 Aug 2026</As_of_date>"
            "<Base_Currency>HKD</Base_Currency>"
            "<Number_of_Stocks>30</Number_of_Stocks>"
            "<Stock_Asset>99.00%</Stock_Asset>"
            "<Cash_Equivalent_Asset>1.00%</Cash_Equivalent_Asset>"
            "<Stock_Code>3466_Unlisted</Stock_Code>"
            + "".join(rows)
            + "</ETFS>"
        )
        return xml.encode("utf-16")

    def test_parse_holdings_xml_validates_full_codes_and_weights(self):
        metadata, rows = update_data.parse_holdings_xml(self.holdings_xml())
        self.assertEqual(metadata["holdings_as_of"], "2026-08-03")
        self.assertEqual(metadata["holding_weight_total_pct"], 99.0)
        self.assertEqual(rows[0]["symbol"], "00001")
        self.assertEqual(rows[0]["full_symbol"], "00001.HK")
        self.assertEqual(rows[0]["weight_pct"], 3.3)

    def test_parse_holdings_xml_rejects_duplicate_symbols(self):
        with self.assertRaisesRegex(RuntimeError, "validation failed"):
            update_data.parse_holdings_xml(self.holdings_xml(duplicate=True))

    def test_parse_hkex_profile_uses_short_official_business_introduction(self):
        payload = {
            "data": {
                "responsecode": "000",
                "quote": {
                    "product_type": "EQTY",
                    "sym": "371",
                    "nm_s": "北控水务集团",
                    "summary": "北控水务集团有限公司是一家主要从事水务业务的公司。该公司通过四个部门运营业务。",
                    "hsic_sub_sector_classification": "水务",
                    "db_updatetime": "2026年8月5日09:36",
                },
            },
            "qid": "00371",
        }
        profile = update_data.parse_hkex_profile(
            f"hkexProfileCallback({json.dumps(payload, ensure_ascii=False)})", "00371"
        )
        self.assertEqual(profile["company_name_zh"], "北控水务集团")
        self.assertEqual(
            profile["business_summary"],
            "北控水务集团有限公司是一家主要从事水务业务的公司。",
        )
        self.assertEqual(profile["industry_zh"], "水务")

    def test_fetch_constituents_requires_and_merges_three_official_sources(self):
        index_metadata = {"constituent_count": 30, "official_updated_at": "2026-08-05"}
        index_rows = [
            {"symbol": str(index).zfill(5), "name": f"Index {index}", "share_type": "O"}
            for index in range(1, 31)
        ]
        holdings_metadata = {"holdings_count": 30, "holdings_as_of": "2026-08-03"}
        holdings = [
            {
                "symbol": str(index).zfill(5),
                "full_symbol": f"{index:05d}.HK",
                "fund_name": f"Fund {index}",
                "fund_name_zh": f"基金 {index}",
                "sector": "Industrials",
                "sector_zh": "工业",
                "weight_pct": float(index),
            }
            for index in range(1, 31)
        ]
        originals = (
            update_data.fetch_index_constituents,
            update_data.fetch_fund_holdings,
            update_data.fetch_hkex_access_token,
            update_data.fetch_hkex_profile,
        )
        update_data.fetch_index_constituents = lambda: (index_metadata, index_rows)
        update_data.fetch_fund_holdings = lambda: (holdings_metadata, holdings)
        update_data.fetch_hkex_access_token = lambda: "public-token"
        update_data.fetch_hkex_profile = lambda symbol, token: {
            "company_name_zh": f"公司 {symbol}",
            "business_summary": f"主营业务 {symbol}",
            "industry_zh": "工业",
            "profile_updated_at": "2026-08-05",
        }
        try:
            metadata, rows = update_data.fetch_constituents()
        finally:
            (
                update_data.fetch_index_constituents,
                update_data.fetch_fund_holdings,
                update_data.fetch_hkex_access_token,
                update_data.fetch_hkex_profile,
            ) = originals

        self.assertTrue(metadata["holdings_match_constituents"])
        self.assertEqual(metadata["profiles_count"], 30)
        self.assertEqual(rows[0]["full_symbol"], "00030.HK")
        self.assertEqual(rows[-1]["business_summary"], "主营业务 00001")

    def test_fetch_constituents_rejects_membership_and_portfolio_mismatch(self):
        index_rows = [
            {"symbol": str(index).zfill(5), "name": f"Index {index}", "share_type": "O"}
            for index in range(1, 31)
        ]
        holdings = [
            {"symbol": str(index).zfill(5), "weight_pct": 3.3}
            for index in range(2, 32)
        ]
        originals = update_data.fetch_index_constituents, update_data.fetch_fund_holdings
        update_data.fetch_index_constituents = lambda: ({"constituent_count": 30}, index_rows)
        update_data.fetch_fund_holdings = lambda: ({"holdings_count": 30}, holdings)
        try:
            with self.assertRaisesRegex(RuntimeError, "symbols do not match"):
                update_data.fetch_constituents()
        finally:
            update_data.fetch_index_constituents, update_data.fetch_fund_holdings = originals

    def test_fetch_hkex_access_token_ignores_commented_sample(self):
        page = """
        <script>
        LabCI.getToken = function () {
            //return "Base64-AES-Encrypted-Token";
            return "official-public-widget-token";
        };
        </script>
        """
        original = update_data.fetch_text
        update_data.fetch_text = lambda *args, **kwargs: page
        try:
            token = update_data.fetch_hkex_access_token()
        finally:
            update_data.fetch_text = original
        self.assertEqual(token, "official-public-widget-token")


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

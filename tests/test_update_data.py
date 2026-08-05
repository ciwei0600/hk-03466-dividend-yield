import importlib.util
import unittest
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


if __name__ == "__main__":
    unittest.main()

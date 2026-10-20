from pathlib import Path
from datetime import date, timedelta
import json
import math
import unittest
from research.scenarios import direction_return
from scripts.check_public import validate_url
from scripts.summarize import summarize

ROOT = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/crypto-calls.json").read_text())

    def test_admitted_schema_contains_no_source_fulltext_or_work_records(self):
        keys = {"audit_id", "person", "date", "source_url", "symbol", "category", "direction", "summary_zh", "eligible", "verification", "scenarios"}
        for row in self.data["calls"]:
            self.assertEqual(set(row), keys)
            self.assertLessEqual(len(row["summary_zh"]), 200)
            self.assertTrue(any("\u4e00" <= char <= "\u9fff" for char in row["summary_zh"]))
            validate_url(row["source_url"])
            self.assertLessEqual(set(row["verification"]), {"result", "deadline"})

    def test_saved_complete_returns_and_dates_are_internally_consistent(self):
        checked = 0
        for row in self.data["calls"]:
            for horizon, result in row["scenarios"].items():
                entry = date.fromisoformat(row["date"]) + timedelta(days=1)
                self.assertEqual(result["entry_date"], str(entry))
                self.assertEqual(result["exit_date"], str(entry + timedelta(days=int(horizon))))
                if result["status"] != "complete":
                    continue
                checked += 1
                self.assertTrue(row["eligible"])
                self.assertLessEqual(result["exit_date"], self.data["price_cutoff"])
                self.assertAlmostEqual(result["gross_return"], direction_return(result["entry_price"], result["exit_price"], row["direction"]), places=12)
                self.assertLessEqual(result["max_drawdown"], 0)
                self.assertTrue(math.isfinite(result["max_drawdown"]))
        self.assertEqual(checked, 815)

    def test_missing_or_pending_is_not_counted_as_a_completed_result(self):
        result = summarize()
        self.assertEqual(result["call_records"], 436)
        self.assertEqual(result["strict_verification"], {"correct": 3, "incorrect": 2, "pending": 3, "unscored": 428})
        self.assertEqual(result["fixed_horizon_scenarios"], {"complete": 815, "pending": 369, "unavailable": 560})

    def test_momentum_metrics_are_finite_summaries_not_account_ledgers(self):
        data = json.loads((ROOT / "data/momentum-metrics.json").read_text())
        self.assertEqual(data["base_simulated_capital"], 100)
        self.assertEqual(len(data["groups"]), 6)
        for name, group in data["groups"].items():
            date.fromisoformat(data["group_cutoffs"][name])
            for row in group.values():
                self.assertGreater(row["end_wealth"], 0)
                self.assertLessEqual(row["max_drawdown"], 0)
                self.assertNotIn("shares", row)

    def test_all_catalog_source_links_are_unsigned_https(self):
        data = json.loads((ROOT / "data/sources.json").read_text())
        for rows in data.values():
            for row in rows:
                self.assertEqual(set(row), {"description", "url"})
                validate_url(row["url"])

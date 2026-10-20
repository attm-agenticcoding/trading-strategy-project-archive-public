import unittest
from research.scenarios import evaluate, direction_return
from research.tax import settle_gain


class MethodTests(unittest.TestCase):
    def setUp(self):
        self.closes = {"2024-01-02": 100, "2024-01-03": 80, "2024-01-04": 120}

    def test_entry_is_next_day_not_publication_day(self):
        self.closes["2024-01-01"] = 1000
        result = evaluate("2024-01-01", 2, "long", self.closes, "2024-01-04")
        self.assertEqual(result["entry_date"], "2024-01-02")
        self.assertAlmostEqual(result["gross_return"], .2)
        self.assertAlmostEqual(result["max_drawdown"], -.2)

    def test_short_uses_price_direction_not_compounded_inverse(self):
        self.assertAlmostEqual(direction_return(100, 120, "short"), -.2)
        result = evaluate("2024-01-01", 2, "short", self.closes, "2024-01-04")
        self.assertAlmostEqual(result["max_drawdown"], 0.8 / 1.2 - 1)

    def test_missing_day_does_not_shift_entry_or_fill(self):
        del self.closes["2024-01-03"]
        self.assertEqual(evaluate("2024-01-01", 2, "long", self.closes, "2024-01-04")["status"], "unavailable")
        del self.closes["2024-01-02"]
        self.assertNotIn("entry_price", evaluate("2024-01-01", 2, "long", self.closes, "2024-01-04"))

    def test_future_deadline_remains_pending(self):
        self.assertEqual(evaluate("2024-01-01", 2, "long", self.closes, "2024-01-03")["status"], "pending")

    def test_ineligible_is_not_silently_scored(self):
        result = evaluate("2024-01-01", 2, None, self.closes, "2024-01-04", eligible=False)
        self.assertEqual(result["status"], "unavailable")

    def test_invalid_input_rejected(self):
        for price in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                direction_return(price, 100, "long")
        with self.assertRaises(ValueError):
            evaluate("2024-01-01", 0, "long", self.closes, "2024-01-04")

    def test_loss_carryforward_never_generates_outside_refund(self):
        tax, bank, used = settle_gain(-30, 0, 1/3, True)
        self.assertEqual((tax, bank, used), (0, 30, 0))
        self.assertEqual(settle_gain(20, bank, 1/3, True), (0, 10, 20))
        tax, bank, used = settle_gain(40, 10, 1/3, True)
        self.assertEqual((tax, bank, used), (10, 0, 10))

    def test_disabled_carryforward_preserves_loss_bank(self):
        self.assertEqual(settle_gain(-20, 5, .25, False), (0, 5, 0))
        self.assertEqual(settle_gain(20, 5, .25, False), (5, 5, 0))

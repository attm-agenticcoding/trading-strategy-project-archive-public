import unittest
from unittest.mock import patch
from research import fetch_prices as prices


def candle(day, low=90, high=110):
    stamp = prices.epoch_ms(day)
    return [stamp, "100", str(high), str(low), "105", "10", stamp + prices.DAY_MS - 1, "0", 0, "0", "0", "0"]


class PriceValidationTests(unittest.TestCase):
    def test_complete_utc_candles_are_accepted(self):
        rows = [candle("2024-01-01"), candle("2024-01-02")]
        prices.validate_daily(rows, rows[0][0], rows[-1][6])

    def test_missing_day_and_bad_ohlc_are_rejected(self):
        rows = [candle("2024-01-01"), candle("2024-01-03")]
        with self.assertRaises(ValueError):
            prices.validate_daily(rows, rows[0][0], rows[-1][6])
        row = candle("2024-01-01", low=106)
        with self.assertRaises(ValueError):
            prices.validate_daily([row], row[0], row[6])

    def test_incomplete_day_is_rejected(self):
        row = candle("2024-01-01")
        row[6] -= 1
        with self.assertRaises(ValueError):
            prices.validate_daily([row], row[0], row[0] + prices.DAY_MS - 1)

    def test_nonadvancing_pagination_is_rejected_without_network(self):
        row = candle("2024-01-01")
        # A claimed page containing an out-of-window row must fail rather than loop.
        with patch.object(prices, "request_json", return_value=(b"[]", [row])):
            with self.assertRaises(ValueError):
                prices.fetch_pages("BTCUSDT", row[0] + prices.DAY_MS, row[6] + prices.DAY_MS)

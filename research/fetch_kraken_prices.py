#!/usr/bin/env python3
"""Keep independent Kraken USD daily evidence; never splice into Binance data.

Kraken only returns the latest 720 candles; it cannot supply older candles via
pagination. The current unfinished candle is discarded. Refresh errors preserve
prior successful files. The first returned day explicitly limits coverage.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import urllib.parse
import urllib.request

from fetch_prices import ROOT, atomic_bytes, atomic_json, epoch_ms, date_of, last_complete_day, utc_now

BASE = "https://api.kraken.com/0/public/OHLC"
DOCS = "https://docs.kraken.com/api-reference/market-data/get-ohlc-data"


def fetch(symbol, start="2024-11-08", end=None):
    end = end or last_complete_day()
    path = ROOT / "prices-kraken" / f"{symbol}.json"
    url = BASE + "?" + urllib.parse.urlencode({"pair": symbol + "USD", "interval": 1440, "since": epoch_ms(start) // 1000})
    try:
        if end > last_complete_day():
            raise ValueError("Cannot include unfinished UTC day")
        with urllib.request.urlopen(url, timeout=45) as response:
            raw = response.read()
        data = json.loads(raw)
        if data["error"]:
            raise ValueError(str(data["error"]))
        pairs = [key for key in data["result"] if key != "last"]
        if len(pairs) != 1:
            raise ValueError("Ambiguous Kraken result pair")
        rows = [row for row in data["result"][pairs[0]] if start <= date_of(row[0] * 1000) <= end]
        if not rows:
            raise ValueError("No completed daily candles in requested range")
        for index, row in enumerate(rows):
            if row[0] % 86400 or (index and row[0] != rows[index - 1][0] + 86400):
                raise ValueError("UTC daily sequence gap or duplicate")
            o, h, low, c = map(float, row[1:5])
            if not all(math.isfinite(x) and x > 0 for x in [o, h, low, c]) or not low <= min(o, c) <= max(o, c) <= h:
                raise ValueError("Invalid OHLC")
        first, last = date_of(rows[0][0] * 1000), date_of(rows[-1][0] * 1000)
        if path.exists():
            previous = json.loads(path.read_text())
            if first > previous["first_date"] or last < previous["last_date"]:
                raise ValueError("Refusing to truncate prior successful saved coverage")
        run = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        raw_file = f"raw/prices-kraken/{symbol}-{run}.json"
        atomic_bytes(ROOT / raw_file, raw)
        output = {"symbol": symbol, "pair": pairs[0], "quote_currency": "USD", "source": "Kraken Spot public OHLC API", "source_url": url, "source_documentation": DOCS, "interval": "1d", "timezone": "UTC", "retrieved_at_utc": utc_now(), "requested_start": start, "requested_end_inclusive": end, "first_date": first, "last_date": last, "candle_count": len(rows), "internal_missing_dates": [], "coverage_starts_after_request": first > start, "coverage_ends_before_request": last < end, "raw_file": raw_file, "raw_sha256": hashlib.sha256(raw).hexdigest(), "coverage_note": "Independent USD-quoted venue. API returns at most its latest 720 candles; older data cannot be retrieved through this endpoint. Current incomplete UTC candle discarded. No Binance data spliced.", "candles": [{"date": date_of(row[0] * 1000), "open_time_ms": row[0] * 1000, "close_time_ms": (row[0] + 86400) * 1000 - 1, "open": float(row[1]), "high": float(row[2]), "low": float(row[3]), "close": float(row[4]), "volume": float(row[6])} for row in rows]}
        atomic_json(path, output)
        return {"symbol": symbol, "status": "ok", "first_date": first, "last_date": last, "candle_count": len(rows), "file": str(path.relative_to(ROOT))}
    except Exception as error:
        return {"symbol": symbol, "status": "error", "error": str(error), "prior_successful_file_preserved": path.exists()}


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, ["BTC", "ETH", "SOL", "ZEC", "HYPE"]))
    atomic_json(ROOT / "prices-kraken" / "metadata.json", {"retrieved_at_utc": utc_now(), "source": BASE, "latest_attempts": results})
    print(json.dumps(results, indent=2))

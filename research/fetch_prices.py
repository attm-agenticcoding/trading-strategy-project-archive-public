#!/usr/bin/env python3
"""Fetch and validate public Binance Spot OHLC data without credentials.

All date arguments use UTC; --end is inclusive and may not include an unfinished
day. Original response bytes are retained with SHA-256 and request URLs. A failed
refresh never replaces the prior successful symbol file. New listings begin at
their first observed candle; missing pre-listing history is never synthesized.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = "https://data-api.binance.vision/api/v3/klines"
DOCS = "https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data"
DAY_MS = 86_400_000
SYMBOLS = ["BTC", "ETH", "SOL", "WIF", "BONK", "DOGE", "ZEC", "XPL", "HYPE", "ENA", "UNI", "AAVE", "SUI", "PEPE", "TAO", "LINK", "JTO", "VIRTUAL", "PUMP", "ETHBTC"]
NATIVE_PAIRS = {"ETHBTC":"BTC", "SOLBTC":"BTC", "LINKBTC":"BTC", "SOLETH":"ETH", "ZECBTC":"BTC"}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def last_complete_day():
    return (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()


def epoch_ms(date):
    return int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time.min, dt.timezone.utc).timestamp() * 1000)


def date_of(timestamp):
    return dt.datetime.fromtimestamp(timestamp / 1000, dt.timezone.utc).date().isoformat()


def atomic_json(path, value):
    return atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def atomic_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".fetch-", delete=False) as handle:
        staged = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def request_json(url):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "CryptoTweetAudit/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=45) as response:
                content = response.read()
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                raise ValueError(f"Unexpected Binance response: {parsed}")
            return content, parsed
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")[:500]
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise ValueError(f"HTTP {error.code}: {body}") from error
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def fetch_pages(pair, start_ms, end_ms, interval="1d", interval_ms=DAY_MS):
    cursor, pages, all_rows = start_ms, [], []
    while cursor <= end_ms:
        url = BASE + "?" + urllib.parse.urlencode({"symbol": pair, "interval": interval, "startTime": cursor, "endTime": end_ms, "limit": 1000})
        raw, rows = request_json(url)
        pages.append({"url": url, "retrieved_at_utc": utc_now(), "content": raw})
        if not rows:
            break
        for row in rows:
            if len(row) < 12 or not cursor <= int(row[0]) <= end_ms:
                raise ValueError("Unexpected candle timestamp or schema")
        all_rows.extend(rows)
        next_cursor = int(rows[-1][0]) + interval_ms
        if next_cursor <= cursor:
            raise ValueError("Pagination did not advance")
        cursor = next_cursor
        if len(rows) < 1000:
            break
    return pages, all_rows


def validate_daily(rows, start_ms, end_ms):
    if not rows:
        raise ValueError("No candles returned; symbol unavailable or outside listing dates")
    previous = None
    for row in rows:
        timestamp, close_time = int(row[0]), int(row[6])
        if timestamp % DAY_MS or close_time != timestamp + DAY_MS - 1:
            raise ValueError("Daily candle is not aligned to a complete UTC day")
        if timestamp < start_ms or close_time > end_ms:
            raise ValueError("Candle falls outside the requested completed-day interval")
        if previous is not None and timestamp != previous + DAY_MS:
            raise ValueError(f"Internal duplicate/date gap: {date_of(previous)} to {date_of(timestamp)}")
        o, h, low, c = map(float, row[1:5])
        if not all(math.isfinite(x) and x > 0 for x in [o, h, low, c]):
            raise ValueError("Nonpositive or nonfinite OHLC price")
        if not low <= min(o, c) <= max(o, c) <= h:
            raise ValueError("Invalid OHLC ordering")
        previous = timestamp


def persist_pages(pages, symbol, interval, run_id):
    result = []
    for index, page in enumerate(pages):
        relative = Path("raw/prices") / symbol / f"{run_id}-{interval}-{index + 1:03d}.json"
        atomic_bytes(ROOT / relative, page["content"])
        result.append({"url": page["url"], "retrieved_at_utc": page["retrieved_at_utc"], "file": str(relative), "sha256": hashlib.sha256(page["content"]).hexdigest()})
    return result


def fetch_symbol(symbol, start, end):
    pair = symbol if symbol in NATIVE_PAIRS else symbol + "USDT"
    previous_path = ROOT / "prices" / f"{symbol}.json"
    attempt = {"symbol": symbol, "pair": pair, "requested_start": start, "requested_end_inclusive": end, "attempted_at_utc": utc_now()}
    try:
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
        if previous:
            if end < previous["last_date"]:
                raise ValueError("Refusing to truncate a prior successful series")
            start = min(start, previous["first_date"], previous.get("requested_start", start))
            for evidence in previous.get("raw_responses", []):
                if hashlib.sha256((ROOT / evidence["file"]).read_bytes()).hexdigest() != evidence["sha256"]:
                    raise ValueError("Saved raw response hash mismatch; prior data preserved")
        start_ms, end_ms = epoch_ms(start), epoch_ms(end) + DAY_MS - 1
        pages, rows = fetch_pages(pair, start_ms, end_ms)
        # A delisting may end the final candle intraday. Preserve its raw response,
        # but never use that partial day or discard the earlier complete history.
        omitted_terminal_dates = []
        if rows:
            last_open, last_close = int(rows[-1][0]), int(rows[-1][6])
            if last_open % DAY_MS == 0 and last_open <= last_close < last_open + DAY_MS - 1:
                omitted_terminal_dates = [date_of(last_open)]
                rows = rows[:-1]
        validate_daily(rows, start_ms, end_ms)
        if previous and (date_of(rows[0][0]) > previous["first_date"] or date_of(rows[-1][0]) < previous["last_date"]):
            raise ValueError("Refresh lost prior successful coverage; prior data preserved")
        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        raw_responses = persist_pages(pages, symbol, "1d", run_id)
        document = {
            "symbol": symbol, "pair": pair, "quote_currency": NATIVE_PAIRS.get(pair,"USDT"),
            "source": "Binance Spot public market-data API", "source_url": BASE, "source_documentation": DOCS,
            "interval": "1d", "timezone": "UTC", "retrieved_at_utc": utc_now(),
            "requested_start": start, "requested_end_inclusive": end,
            "first_date": date_of(rows[0][0]), "last_date": date_of(rows[-1][0]),
            "candle_count": len(rows), "internal_missing_dates": [],
            "coverage_starts_after_request": int(rows[0][0]) > start_ms,
            "coverage_ends_before_request": int(rows[-1][6]) < end_ms,
            "omitted_partial_terminal_dates": omitted_terminal_dates,
            "coverage_note": "Observed complete candles only. Partial terminal delisting candles are excluded and retained in raw responses. Dates outside the observed listing history are not backfilled. USDT quotes are not treated as an exact USD price.",
            "raw_responses": raw_responses,
            "candles": [{"date": date_of(row[0]), "open_time_ms": row[0], "close_time_ms": row[6], "open": float(row[1]), "high": float(row[2]), "low": float(row[3]), "close": float(row[4]), "volume": float(row[5])} for row in rows],
        }
        atomic_json(previous_path, document)
        return {**attempt, "status": "ok", "file": f"prices/{symbol}.json", "first_date": document["first_date"], "last_date": document["last_date"], "candle_count": len(rows), "coverage_starts_after_request": document["coverage_starts_after_request"], "coverage_ends_before_request": document["coverage_ends_before_request"]}
    except Exception as error:
        return {**attempt, "status": "error", "error": str(error), "prior_successful_file_preserved": previous_path.exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2021-10-15")
    parser.add_argument("--end", default=last_complete_day())
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.start > args.end or args.end > last_complete_day():
        parser.error("Require start <= end <= the last completed UTC day")
    if any(not symbol.isalnum() or not symbol.isupper() for symbol in args.symbols):
        parser.error("Symbols must contain uppercase letters/numbers only")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(6, args.workers))) as pool:
        attempts = list(pool.map(lambda symbol: fetch_symbol(symbol, args.start, args.end), args.symbols))
    metadata_path = ROOT / "prices" / "metadata.json"
    previous = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    series = {item["symbol"]: item for item in previous.get("series", [])}
    for item in attempts:
        if item["status"] == "ok" or item["symbol"] not in series:
            series[item["symbol"]] = item
    metadata = {"generated_at_utc": utc_now(), "requested_start": args.start, "requested_end_inclusive": args.end, "source": BASE, "calendar": "UTC daily, 7 days/week", "series": sorted(series.values(), key=lambda item: item["symbol"]), "latest_refresh_attempts": attempts}
    atomic_json(metadata_path, metadata)
    print(json.dumps(attempts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

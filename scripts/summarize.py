"""Summarize admitted public records without fetching or changing data."""
from pathlib import Path
from collections import Counter
import json

ROOT = Path(__file__).resolve().parents[1]


def summarize():
    data = json.loads((ROOT / "data/crypto-calls.json").read_text())
    return {
        "snapshot_date": data["snapshot_date"],
        "price_cutoff": data["price_cutoff"],
        "call_records": len(data["calls"]),
        "unique_source_urls": len({row["source_url"] for row in data["calls"]}),
        "strict_verification": dict(Counter(row["verification"]["result"] for row in data["calls"])),
        "fixed_horizon_scenarios": dict(Counter(s["status"] for row in data["calls"] for s in row["scenarios"].values())),
    }


if __name__ == "__main__":
    print(json.dumps(summarize(), ensure_ascii=False, indent=2))

"""Portable fixed-horizon direction scenarios, adapted from existing research.

Inputs are caller-supplied UTC-date closing prices. No fetching or trading occurs.
"""
from datetime import date, timedelta
import math


def direction_return(entry, exit_price, direction):
    if direction not in {"long", "short"}:
        raise ValueError("Require an explicit long or short direction")
    if not all(math.isfinite(x) and x > 0 for x in (entry, exit_price)):
        raise ValueError("Prices must be finite and positive")
    return (1 if direction == "long" else -1) * (exit_price / entry - 1)


def evaluate(published_date, horizon_days, direction, closes, cutoff, eligible=True):
    if not isinstance(horizon_days, int) or isinstance(horizon_days, bool) or horizon_days <= 0:
        raise ValueError("Require a positive integer calendar-day horizon")
    entry = date.fromisoformat(published_date) + timedelta(days=1)
    end = entry + timedelta(days=horizon_days)
    cutoff = date.fromisoformat(cutoff)
    result = {"entry_date": str(entry), "exit_date": str(end), "status": "unavailable"}
    if not eligible:
        return result
    if direction not in {"long", "short"}:
        raise ValueError("Eligible observations need an explicit direction")
    if str(entry) not in closes:
        return result
    p0 = closes[str(entry)]
    direction_return(p0, p0, direction)
    result["entry_price"] = p0
    if end > cutoff:
        result["status"] = "pending"
        return result
    days = [str(entry + timedelta(days=i)) for i in range(horizon_days + 1)]
    if any(day not in closes for day in days):
        return result
    peak, drawdown = 1.0, 0.0
    for day in days:
        nav = 1 + direction_return(p0, closes[day], direction)
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
    result.update(status="complete", exit_price=closes[str(end)],
                  gross_return=direction_return(p0, closes[str(end)], direction),
                  max_drawdown=drawdown)
    return result

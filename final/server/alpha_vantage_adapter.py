from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List

import httpx

from config import settings

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


@dataclass
class PricePoint:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def _ensure_api_key() -> str:
    """
    Return the Alpha Vantage API key from settings or raise a clear error.
    """
    api_key = (
        getattr(settings, "alpha_vantage_api_key", None)
        or getattr(settings, "alphavantage_api_key", None)
    )
    if not api_key:
        raise RuntimeError(
            "Alpha Vantage API key not configured. "
            "Set ALPHA_VANTAGE_API_KEY in the environment."
        )
    return api_key


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def get_price_series_for_ticker(
    ticker: str,
    start_date: date,
    end_date: date,
    max_points: int = 60,
) -> List[Dict[str, Any]]:
    """
    Fetch daily price series for ticker from Alpha Vantage TIME_SERIES_DAILY
    and return a list of dicts sorted by date.

    The list is filtered to [start_date, end_date] inclusive and truncated to
    at most max_points most recent entries.
    """
    if start_date > end_date:
        raise RuntimeError(f"start_date {start_date} is after end_date {end_date}.")

    api_key = _ensure_api_key()

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker.upper(),
        "outputsize": "compact",  # last ~100 days
        "apikey": api_key,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(ALPHA_VANTAGE_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Alpha Vantage HTTP request failed: {exc}") from exc

    data = resp.json()
    ts = data.get("Time Series (Daily)")

    if not isinstance(ts, dict):
        note = data.get("Note") or data.get("Information") or data.get("Error Message")
        raise RuntimeError(
            "Alpha Vantage response missing 'Time Series (Daily)'. "
            f"Check API key, rate limits, and parameters. Extra info: {note!r}"
        )

    points: List[PricePoint] = []

    for date_str, fields in ts.items():
        try:
            d = _parse_date(date_str)
        except ValueError:
            continue

        if d < start_date or d > end_date:
            continue

        try:
            open_ = float(fields["1. open"])
            high = float(fields["2. high"])
            low = float(fields["3. low"])
            close = float(fields["4. close"])
            volume = int(float(fields["5. volume"]))
        except (KeyError, ValueError, TypeError):
            continue

        points.append(
            PricePoint(
                date=d.isoformat(),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )

    # Sort ascending by date and keep only the most recent max_points entries
    points.sort(key=lambda p: p.date)
    if max_points and len(points) > max_points:
        points = points[-max_points:]

    return [
        {
            "date": p.date,
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        }
        for p in points
    ]
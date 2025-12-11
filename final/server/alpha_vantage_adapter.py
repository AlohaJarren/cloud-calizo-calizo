from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

import httpx

from config import settings

ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"


def get_price_series_for_ticker(
    ticker: str,
    start_date: date,
    end_date: date,
    resolution: str = "D",
) -> List[Dict[str, Any]]:
    """
    Fetch daily price series for a ticker from Alpha Vantage.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g., "AAPL").
    start_date : date
        Inclusive start of the date range filter.
    end_date : date
        Inclusive end of the date range filter.
    resolution : str
        Granularity hint, currently ignored because we always use
        TIME_SERIES_DAILY for the free tier. Kept for future extension.

    Returns
    -------
    List[Dict[str, Any]]
        A list of daily OHLCV bars, sorted by date ascending. Each element
        is a JSON-serializable dict.
    """
    api_key = settings.alphavantage_api_key
    if not api_key:
        raise RuntimeError(
            "Alpha Vantage API key not configured. "
            "Set ALPHAVANTAGE_API_KEY in the environment."
        )

    if start_date > end_date:
        raise RuntimeError("start_date must be on or before end_date.")

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker.upper(),
        "outputsize": "compact",
        "apikey": api_key,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(ALPHAVANTAGE_BASE_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Alpha Vantage HTTP request failed: {exc}") from exc

    data = resp.json()

    # Alpha Vantage uses "Error Message" and "Note" to signal problems,
    # but still returns HTTP 200 in many of these cases.
    if "Error Message" in data:
        raise RuntimeError(f"Alpha Vantage error: {data['Error Message']}")
    if "Note" in data:
        raise RuntimeError(f"Alpha Vantage note: {data['Note']}")

    ts_key = "Time Series (Daily)"
    if ts_key not in data:
        raise RuntimeError(
            "Alpha Vantage response missing 'Time Series (Daily)'. "
            "Check the API key and parameters or call frequency limits."
        )

    ts = data[ts_key]
    if not isinstance(ts, dict):
        raise RuntimeError(
            "Alpha Vantage time series data is not a dictionary as expected."
        )

    points: List[Dict[str, Any]] = []

    for date_str, bar in ts.items():
        try:
            bar_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            # Skip unexpected keys that are not ISO dates
            continue

        if bar_date < start_date or bar_date > end_date:
            continue

        # Alpha Vantage daily bars use these keys
        try:
            open_val = float(bar.get("1. open"))
            high_val = float(bar.get("2. high"))
            low_val = float(bar.get("3. low"))
            close_val = float(bar.get("4. close"))
            volume_val = int(bar.get("5. volume"))
        except (TypeError, ValueError) as exc:
            # If any conversion fails, skip this bar rather than failing the whole call
            continue

        points.append(
            {
                "date": bar_date.isoformat(),
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": volume_val,
            }
        )

    # Sort by date ascending to make it nicer for the client/agent
    points.sort(key=lambda p: p["date"])

    return points
from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, List

import httpx

from config import settings


def _parse_iso_date(date_str: str) -> date:
    """
    Parse an ISO date string (YYYY-MM-DD) into a date object.

    Raises ValueError if the format is invalid.
    """
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.") from exc

    return dt.date()


def get_price_series_for_ticker(
    ticker: str,
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    """
    Fetch historical daily OHLCV price data for a ticker from Alpha Vantage.

    This uses the TIME_SERIES_DAILY endpoint, which is available on the
    free tier (subject to the daily rate limits). We request the compact
    output size (last ~100 data points) and then filter by the requested
    date range.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol, for example "AAPL".
    start_date : str
        Start date in ISO format, "YYYY-MM-DD". Inclusive.
    end_date : str
        End date in ISO format, "YYYY-MM-DD". Inclusive.

    Returns
    -------
    List[Dict[str, Any]]
        A list of price points, each with keys:
        date, open, high, low, close, volume.

    Requirements
    ------------
    - ALPHAVANTAGE_API_KEY must be set in the environment.
    """
    if not settings.alphavantage_api_key:
        raise RuntimeError(
            "ALPHAVANTAGE_API_KEY is not set. Please configure it in .env or "
            "as an environment variable."
        )

    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)

    if end_dt < start_dt:
        raise ValueError("end_date must be on or after start_date.")

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",          # free-tier endpoint
        "symbol": ticker.upper(),
        "outputsize": "compact",                  # ~100 most recent days
        "apikey": settings.alphavantage_api_key,
    }

    try:
        resp = httpx.get(url, params=params, timeout=10.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Alpha Vantage HTTP request failed: {exc}") from exc

    if resp.status_code >= 400:
        # Try to surface Alpha Vantage's error message to the caller.
        try:
            err_payload = resp.json()
        except Exception:
            err_payload = resp.text
        raise RuntimeError(
            f"Alpha Vantage returned HTTP {resp.status_code}: {err_payload}"
        )

    data = resp.json()

    # Alpha Vantage uses:
    # - "Error Message" for invalid calls or invalid/missing API key.
    # - "Note" for throttling / too many requests.
    # - "Information" for premium-only endpoints or other info messages.
    error_msg = data.get("Error Message")
    if error_msg:
        raise RuntimeError(f"Alpha Vantage error: {error_msg}")

    note_msg = data.get("Note")
    if note_msg:
        raise RuntimeError(f"Alpha Vantage note: {note_msg}")

    info_msg = data.get("Information")
    if info_msg:
        raise RuntimeError(f"Alpha Vantage info: {info_msg}")

    ts_key = "Time Series (Daily)"
    ts = data.get(ts_key)
    if not isinstance(ts, dict):
        top_level_keys = list(data.keys())
        raise RuntimeError(
            "Alpha Vantage response missing 'Time Series (Daily)'. "
            f"Top-level keys: {top_level_keys}. "
            "Check ALPHAVANTAGE_API_KEY, symbol, and free-tier limits."
        )

    points: List[Dict[str, Any]] = []

    for date_str, day_data in ts.items():
        try:
            current_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            # Skip unexpected date formats.
            continue

        if current_date < start_dt or current_date > end_dt:
            continue

        try:
            open_val = float(day_data["1. open"])
            high_val = float(day_data["2. high"])
            low_val = float(day_data["3. low"])
            close_val = float(day_data["4. close"])
            volume_val = float(day_data["5. volume"])
        except (KeyError, ValueError):
            # Skip rows with missing or malformed fields.
            continue

        points.append(
            {
                "date": current_date.isoformat(),
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": volume_val,
            }
        )

    # Sort by date ascending so downstream consumers can rely on order.
    points.sort(key=lambda p: p["date"])

    return points
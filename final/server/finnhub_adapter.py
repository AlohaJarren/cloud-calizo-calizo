from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import httpx

from config import settings


def _parse_iso_date_to_epoch(date_str: str) -> int:
    """
    Convert an ISO date string (YYYY-MM-DD) to a Unix timestamp (seconds).

    If the date has no timezone, we treat it as UTC.
    """
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return int(dt.timestamp())


def get_price_series_for_ticker(
    ticker: str,
    start_date: str,
    end_date: str,
    resolution: str = "D",
) -> List[Dict[str, Any]]:
    """
    Fetch historical OHLCV price data for a ticker from Finnhub.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol, for example "AAPL".
    start_date : str
        Start date in ISO format, "YYYY-MM-DD".
    end_date : str
        End date in ISO format, "YYYY-MM-DD". Inclusive.
    resolution : str
        Finnhub resolution code. Default is "D" for daily bars.

    Returns
    -------
    List[Dict[str, Any]]
        A list of price points, each with keys:
        date, open, high, low, close, volume.

    Requirements
    ------------
    - FINNHUB_API_KEY must be set in the environment.
    """
    if not settings.finnhub_api_key:
        raise RuntimeError(
            "FINNHUB_API_KEY is not set. Please configure it in .env or "
            "as an environment variable."
        )

    start_ts = _parse_iso_date_to_epoch(start_date)

    # Add almost one day to include the end date.
    end_dt = datetime.fromtimestamp(_parse_iso_date_to_epoch(end_date), tz=timezone.utc)
    end_dt = end_dt + timedelta(days=1) - timedelta(seconds=1)
    end_ts = int(end_dt.timestamp())

    if end_ts < start_ts:
        raise ValueError("end_date must be on or after start_date.")

    url = "https://finnhub.io/api/v1/stock/candle"
    params = {
        "symbol": ticker.upper(),
        "resolution": resolution,
        "from": start_ts,
        "to": end_ts,
        "token": settings.finnhub_api_key,
    }

    try:
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Finnhub HTTP request failed: {exc}") from exc

    data = resp.json()

    status = data.get("s")
    if status == "no_data":
        # No candles for this period; return empty list.
        return []
    if status != "ok":
        raise RuntimeError(f"Finnhub returned error status: {status}")

    closes = data.get("c", [])
    highs = data.get("h", [])
    lows = data.get("l", [])
    opens = data.get("o", [])
    volumes = data.get("v", [])
    timestamps = data.get("t", [])

    length = min(
        len(closes),
        len(highs),
        len(lows),
        len(opens),
        len(volumes),
        len(timestamps),
    )

    points: List[Dict[str, Any]] = []
    for i in range(length):
        ts = timestamps[i]
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        date_str = dt.date().isoformat()

        points.append(
            {
                "date": date_str,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(volumes[i]),
            }
        )

    return points
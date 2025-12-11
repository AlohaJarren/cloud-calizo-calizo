from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date_str(date_str: str) -> datetime:
    # Alpha Vantage uses YYYY-MM-DD for daily series.
    return datetime.strptime(date_str, "%Y-%m-%d")


def compute_technical_indicators(
    price_points: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute simple technical indicators from a list of price points.

    Each price point is expected to have:
      - date (YYYY-MM-DD string)
      - close (float)
    The list is expected to be sorted ascending by date. If it is not,
    we will sort it defensively.
    """
    if not price_points:
        return {
            "has_data": False,
            "point_count": 0,
            "latest_date": None,
            "latest_close": None,
            "change_pct_total": None,
            "sma_5": None,
            "sma_20": None,
            "trend_label": "unknown",
        }

    # Sort defensively by date
    sorted_points = sorted(
        price_points,
        key=lambda p: _parse_date_str(str(p.get("date"))),
    )

    closes = []
    for pt in sorted_points:
        close_val = _safe_float(pt.get("close"))
        if close_val is not None:
            closes.append(close_val)

    if not closes:
        return {
            "has_data": False,
            "point_count": len(price_points),
            "latest_date": sorted_points[-1].get("date"),
            "latest_close": None,
            "change_pct_total": None,
            "sma_5": None,
            "sma_20": None,
            "trend_label": "unknown",
        }

    latest_close = closes[-1]
    first_close = closes[0]

    if first_close and first_close != 0.0:
        change_pct_total = (latest_close - first_close) / first_close * 100.0
    else:
        change_pct_total = None

    def _sma_last(n: int) -> Optional[float]:
        if len(closes) < n:
            return None
        window = closes[-n:]
        return sum(window) / float(len(window))

    sma_5 = _sma_last(5)
    sma_20 = _sma_last(20)

    # Simple trend classification based on total percent change.
    # This is intentionally rough; the LLM can use it as a hint.
    if change_pct_total is None:
        trend_label = "unknown"
    elif change_pct_total > 5.0:
        trend_label = "up"
    elif change_pct_total < -5.0:
        trend_label = "down"
    else:
        trend_label = "sideways"

    return {
        "has_data": True,
        "point_count": len(price_points),
        "latest_date": sorted_points[-1].get("date"),
        "latest_close": latest_close,
        "change_pct_total": change_pct_total,
        "sma_5": sma_5,
        "sma_20": sma_20,
        "trend_label": trend_label,
    }


@dataclass
class FundamentalSnapshot:
    has_data: bool
    latest_row: Dict[str, Any] | None
    ratios: Dict[str, Optional[float]]


def _extract_latest_fundamental_row(
    rows: List[Dict[str, Any]],
) -> Dict[str, Any] | None:
    if not rows:
        return None

    # Try to choose the latest period by a date like column if present.
    # Common names to try: period_end_date, end_date, filing_date.
    def _row_key(row: Dict[str, Any]) -> datetime:
        for key in ("period_end_date", "end_date", "filing_date"):
            if key in row and row[key]:
                try:
                    return datetime.fromisoformat(str(row[key]))
                except ValueError:
                    continue
        # Fallback: treat missing date as very old.
        return datetime.min

    sorted_rows = sorted(rows, key=_row_key)
    return sorted_rows[-1]


def compute_fundamental_ratios(
    fundamentals_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute a few basic ratios from SEC fundamentals style data.

    This function is intentionally defensive about schema. It looks for
    several candidate column names and only computes ratios when both
    numerator and denominator are present and non zero.
    """
    latest = _extract_latest_fundamental_row(fundamentals_rows)
    if latest is None:
        return {
            "has_data": False,
            "latest_period": None,
            "ratios": {},
        }

    # Guess some common fields; you can refine this once you inspect
    # the actual table or view you create in BigQuery.
    revenue = _safe_float(
        latest.get("revenues")
        or latest.get("revenue")
        or latest.get("total_revenue")
    )
    net_income = _safe_float(
        latest.get("net_income")
        or latest.get("net_income_loss")
        or latest.get("income_loss")
    )
    assets = _safe_float(
        latest.get("total_assets")
        or latest.get("assets")
    )
    equity = _safe_float(
        latest.get("shareholders_equity")
        or latest.get("stockholders_equity")
        or latest.get("equity")
    )

    ratios: Dict[str, Optional[float]] = {}

    if revenue is not None and revenue != 0.0:
        if net_income is not None:
            ratios["net_margin"] = net_income / revenue

    if assets is not None and assets != 0.0:
        if revenue is not None:
            ratios["asset_turnover"] = revenue / assets

    if equity is not None and equity != 0.0:
        if net_income is not None:
            ratios["return_on_equity"] = net_income / equity

    # Many SEC datasets have some notion of period end date.
    latest_period = (
        latest.get("period_end_date")
        or latest.get("end_date")
        or latest.get("filing_date")
    )

    return {
        "has_data": True,
        "latest_period": latest_period,
        "ratios": ratios,
    }


def compute_risk_score(
    technical: Dict[str, Any],
    fundamentals: Dict[str, Any],
    sentiment: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Combine technical trend, simple fundamentals, and sentiment into a
    rough risk score in [0, 1], where higher means higher risk.

    This is intentionally simple and interpretable so that in your
    screencast you can explain how the score is produced and how the
    LLM might use it as one signal among many.
    """
    score = 0.5  # start at medium

    # Technical piece: strong up or down move.
    change_pct = technical.get("change_pct_total")
    if isinstance(change_pct, (int, float)):
        if change_pct > 10.0:
            score -= 0.05  # momentum in your favor
        elif change_pct < -10.0:
            score += 0.1   # sharp drawdown, more risk

    # Fundamentals piece: if we have any ratios, trim risk a bit.
    fund_info = fundamentals or {}
    ratios = fund_info.get("ratios") or {}
    if ratios:
        # If net margin or ROE exist and are positive, treat that as modestly de risked.
        net_margin = ratios.get("net_margin")
        roe = ratios.get("return_on_equity")

        if isinstance(net_margin, (int, float)) and net_margin > 0.0:
            score -= 0.05
        if isinstance(roe, (int, float)) and roe > 0.0:
            score -= 0.05

    # Sentiment piece: use aggregate label if present.
    sentiment_label = sentiment.get("aggregate_label")
    if isinstance(sentiment_label, str):
        label_lower = sentiment_label.lower()
        if label_lower == "positive":
            score -= 0.05
        elif label_lower == "negative":
            score += 0.05

    # Clamp to [0, 1]
    if score < 0.0:
        score = 0.0
    if score > 1.0:
        score = 1.0

    if score < 0.33:
        risk_label = "low"
    elif score > 0.66:
        risk_label = "high"
    else:
        risk_label = "medium"

    return {
        "score": score,
        "label": risk_label,
        "inputs": {
            "technical_change_pct_total": change_pct,
            "fundamentals_have_data": bool(fundamentals.get("has_data")),
            "sentiment_label": sentiment_label,
        },
    }
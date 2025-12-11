from __future__ import annotations

from typing import Any, Dict, List

from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

from config import settings

_bq_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    """
    Lazily construct a BigQuery client.

    Uses settings.project_id if provided. If project_id is None, the
    BigQuery client will fall back to ADC's default project.
    """
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=settings.project_id or None)
    return _bq_client


# Minimal mapping from ticker -> integer CIK (no leading zeros).
# You can extend this list if you want to support more tickers.
_TICKER_TO_CIK: Dict[str, int] = {
    "AAPL": 320193,    # Apple Inc. (CIK 0000320193 -> 320193)
    "MSFT": 789019,    # Microsoft Corp. (0000789019 -> 789019)
    "GOOGL": 1652044,  # Alphabet Inc. (0001652044 -> 1652044)
    "GOOG": 1652044,
    "AMZN": 1018724,   # Amazon.com Inc. (0001018724 -> 1018724)
    "META": 1326801,   # Meta Platforms Inc.
    "TSLA": 1318605,   # Tesla Inc.
    "NFLX": 1065280,   # Netflix Inc.
}


def _lookup_cik_for_ticker(ticker: str) -> int:
    """
    Translate a stock ticker symbol into an integer CIK used in the
    sec_quarterly_financials tables.

    The public SEC dataset stores central_index_key as an INT64 with
    leading zeros removed (e.g., 320193 instead of 0000320193).
    """
    key = ticker.strip().upper()
    cik = _TICKER_TO_CIK.get(key)
    if cik is None:
        raise RuntimeError(
            f"No CIK mapping configured for ticker '{ticker}'. "
            "Update _TICKER_TO_CIK in bigquery_adapter.py to support this symbol."
        )
    return cik


def get_fundamentals_for_ticker(
    ticker: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Fetch fundamentals-style records for a given ticker from BigQuery.

    Currently this is wired against the public SEC quarterly dataset
    via BQ_SEC_TABLE_FQN. For example:

        BQ_SEC_TABLE_FQN=bigquery-public-data.sec_quarterly_financials.quick_summary

    We filter by central_index_key (CIK) using a simple ticker -> CIK
    mapping and return up to `limit` rows as a list of dicts.
    """
    if not settings.bq_sec_table_fqn:
        raise RuntimeError(
            "BigQuery SEC fundamentals table not configured. "
            "Set BQ_SEC_TABLE_FQN in the environment to a fully-qualified "
            "table or view name, for example:\n"
            "  BQ_SEC_TABLE_FQN=bigquery-public-data.sec_quarterly_financials.quick_summary"
        )

    # Resolve ticker -> integer CIK used by the SEC dataset.
    cik_int = _lookup_cik_for_ticker(ticker)

    client = _get_client()

    # For the quick_summary table this will give you rows like:
    # central_index_key, company_name, submission_number, fiscal_year,
    # fiscal_period_focus, measure_tag, value, etc.
    query = f"""
    SELECT *
    FROM `{settings.bq_sec_table_fqn}`
    WHERE central_index_key = @cik
    LIMIT @limit_rows
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("cik", "INT64", cik_int),
            bigquery.ScalarQueryParameter("limit_rows", "INT64", int(limit)),
        ]
    )

    try:
        job = client.query(query, job_config=job_config)
        result_iter = job.result()
    except GoogleAPIError as exc:
        # Wrap BigQuery-specific exceptions in a simpler error so upper
        # layers (FastAPI) can convert them to HTTP errors cleanly.
        message = getattr(exc, "message", str(exc))
        raise RuntimeError(f"BigQuery query failed: {message}") from exc

    rows: List[Dict[str, Any]] = []
    for row in result_iter:
        rows.append(dict(row.items()))

    return rows
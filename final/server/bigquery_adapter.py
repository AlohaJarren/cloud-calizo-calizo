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


def get_fundamentals_for_ticker(
    ticker: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Fetch fundamentals records for a given ticker from BigQuery.

    Parameters
    ----------
    ticker : str
        Stock ticker (e.g., "AAPL", "NVDA"). Case-insensitive.
    limit : int
        Maximum number of rows to return (to protect from huge scans).

    Returns
    -------
    List[Dict[str, Any]]
        A list of rows (each row is a dict mapping column name to value).

    Configuration requirements
    --------------------------
    - settings.bq_sec_table_fqn (env var BQ_SEC_TABLE_FQN) must be set
      to a fully-qualified table or view, for example:

          BQ_SEC_TABLE_FQN=cloud-calizo-calizo.quant.sec_fundamentals_view

      The table/view should have at least a "ticker" column; additional
      columns are free-form and will be returned as-is.

    Notes
    -----
    - This function is intentionally generic about schema so that you can
      adapt it by creating a view in BigQuery that presents whatever shape
      you find most useful for quant research.
    """
    if not settings.bq_sec_table_fqn:
        raise RuntimeError(
            "BigQuery SEC fundamentals table not configured. "
            "Set BQ_SEC_TABLE_FQN in the environment to a fully-qualified "
            "table or view name, for example:\n"
            "  BQ_SEC_TABLE_FQN=cloud-calizo-calizo.quant.sec_fundamentals_view"
        )

    client = _get_client()

    # Parameterized query to avoid SQL injection and allow query cache.
    query = f"""
    SELECT *
    FROM `{settings.bq_sec_table_fqn}`
    WHERE UPPER(ticker) = @ticker
    LIMIT @limit_rows
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("ticker", "STRING", ticker.upper()),
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
        # row is a google.cloud.bigquery.table.Row; .items() gives (key, value)
        rows.append(dict(row.items()))

    return rows
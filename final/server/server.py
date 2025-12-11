from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from bigquery_adapter import get_fundamentals_for_ticker
from alpha_vantage_adapter import get_price_series_for_ticker
from newsdata_adapter import get_news_and_sentiment_for_ticker

# Basic logging configuration. In Cloud Run, logs will be captured by
# Cloud Logging and can be filtered by severity, trace, etc.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("final-mcp-server")

app = FastAPI(
    title="CS530 Final - Agentic Quant MCP Server",
    version="0.3.0",
    description=(
        "MCP server that exposes tools over HTTP for an LLM agent client. "
        "Current focus: BigQuery-based fundamentals, Alpha Vantage price "
        "series, and news-driven sentiment signals."
    ),
)


class MCPTool(BaseModel):
    name: str
    description: str
    implemented: bool = Field(
        default=False,
        description="True if this tool is wired to a real backend.",
    )


class MCPCallRequest(BaseModel):
    tool: str = Field(..., description="Name of the MCP tool to invoke.")
    arguments: Dict[str, Any] | None = Field(
        default=None,
        description="JSON arguments for the tool call.",
    )


class MCPCallResponse(BaseModel):
    tool: str
    ok: bool
    data: Any | None = None
    error: Optional[str] = None


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    """
    Simple liveness probe.

    Does not touch external services. Suitable for container orchestration
    health checks.
    """
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> Dict[str, Any]:
    """
    Readiness probe.

    Performs lightweight checks on configuration. We do not ping BigQuery
    on every call, but we can surface missing env vars here for easier
    debugging in Cloud Run.
    """
    missing: List[str] = []

    if not settings.project_id:
        missing.append("PROJECT_ID")

    if not settings.bq_sec_table_fqn:
        missing.append("BQ_SEC_TABLE_FQN")

    status = "ready" if not missing else "degraded"

    return {
        "status": status,
        "project_id": settings.project_id,
        "environment": settings.environment,
        "missing_env": missing,
    }


@app.get("/mcp/tools", response_model=List[MCPTool])
def list_tools() -> List[MCPTool]:
    """
    Describe available tools to the MCP client.

    The client (e.g., a LangChain or MCP-capable agent) can call this to
    discover what tools exist and which ones are implemented in this
    server version.
    """
    return [
        MCPTool(
            name="bq_get_fundamentals",
            description=(
                "Query BigQuery for fundamentals rows for a given ticker, "
                "using a configurable SEC-derived table or view "
                "(BQ_SEC_TABLE_FQN). Returns raw rows for the agent to "
                "analyze and synthesize into buy/hold/sell narratives."
            ),
            implemented=True,
        ),
        MCPTool(
            name="alpha_vantage_get_price_series",
            description=(
                "Get historical daily price time series for a ticker from "
                "Alpha Vantage (TIME_SERIES_DAILY). Intended for technical "
                "signals, back-of-the-envelope indicators, and charting."
            ),
            implemented=True,
        ),
        MCPTool(
            name="news_sentiment_for_ticker",
            description=(
                "Fetch recent news for a ticker using NewsData.io and attach "
                "a simple lexical sentiment score per article plus an "
                "aggregate sentiment summary."
            ),
            implemented=True,
        ),
    ]


def _parse_iso_date(value: str, field_name: str) -> datetime.date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Field "{field_name}" must be in YYYY-MM-DD format.',
        ) from exc


def _handle_bq_get_fundamentals(args: Dict[str, Any] | None) -> MCPCallResponse:
    """
    Internal handler for the bq_get_fundamentals tool.

    Expected arguments:
    - ticker (str; required): stock ticker symbol.
    - limit (int; optional): max number of rows to return (default 100).
    """
    if args is None:
        raise HTTPException(
            status_code=400,
            detail="bq_get_fundamentals requires arguments.",
        )

    ticker = args.get("ticker")
    if not ticker or not isinstance(ticker, str):
        raise HTTPException(
            status_code=400,
            detail='bq_get_fundamentals requires a string "ticker" argument.',
        )

    limit_raw = args.get("limit", 100)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail='Optional "limit" must be an integer if provided.',
        )

    logger.info("bq_get_fundamentals called for ticker=%s limit=%s", ticker, limit)

    try:
        rows = get_fundamentals_for_ticker(ticker=ticker, limit=limit)
    except RuntimeError as exc:
        # Config or BigQuery runtime errors
        logger.exception("Error while fetching fundamentals from BigQuery")
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return MCPCallResponse(
        tool="bq_get_fundamentals",
        ok=True,
        data={
            "ticker": ticker.upper(),
            "row_count": len(rows),
            "rows": rows,
        },
    )


def _handle_alpha_vantage_get_price_series(args: Dict[str, Any] | None) -> MCPCallResponse:
    """
    Internal handler for the alpha_vantage_get_price_series tool.

    Expected arguments:
    - ticker (str; required): stock ticker symbol.
    - start_date (str; required): ISO date YYYY-MM-DD.
    - end_date (str; required): ISO date YYYY-MM-DD.
    - resolution (str; optional): granularity, currently ignored by the
      Alpha Vantage adapter which always uses daily bars, but accepted
      for future extensibility.
    """
    if args is None:
        raise HTTPException(
            status_code=400,
            detail="alpha_vantage_get_price_series requires arguments.",
        )

    ticker = args.get("ticker")
    if not ticker or not isinstance(ticker, str):
        raise HTTPException(
            status_code=400,
            detail='alpha_vantage_get_price_series requires a string "ticker" argument.',
        )

    start_raw = args.get("start_date")
    end_raw = args.get("end_date")
    if not isinstance(start_raw, str) or not isinstance(end_raw, str):
        raise HTTPException(
            status_code=400,
            detail='Both "start_date" and "end_date" must be ISO date strings.',
        )

    start_date = _parse_iso_date(start_raw, "start_date")
    end_date = _parse_iso_date(end_raw, "end_date")

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail='"start_date" must be on or before "end_date".',
        )

    resolution = args.get("resolution", "D")

    logger.info(
        "alpha_vantage_get_price_series called for ticker=%s start=%s end=%s res=%s",
        ticker,
        start_date,
        end_date,
        resolution,
    )

    try:
        points = get_price_series_for_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
        )
    except RuntimeError as exc:
        logger.exception("Error while fetching price series from Alpha Vantage")
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return MCPCallResponse(
        tool="alpha_vantage_get_price_series",
        ok=True,
        data={
            "ticker": ticker.upper(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "resolution": resolution,
            "point_count": len(points),
            "points": points,
        },
    )


def _handle_news_sentiment_for_ticker(args: Dict[str, Any] | None) -> MCPCallResponse:
    """
    Internal handler for the news_sentiment_for_ticker tool.

    Expected arguments:
    - ticker (str; required): stock ticker symbol or company keyword.
    - max_articles (int; optional): maximum number of articles to score.
    - language (str; optional): ISO language code (default "en").
    - country (str; optional): ISO country code hint for sources.
    """
    if args is None:
        raise HTTPException(
            status_code=400,
            detail="news_sentiment_for_ticker requires arguments.",
        )

    ticker = args.get("ticker")
    if not ticker or not isinstance(ticker, str):
        raise HTTPException(
            status_code=400,
            detail='news_sentiment_for_ticker requires a string "ticker" argument.',
        )

    max_articles_raw = args.get("max_articles", 10)
    try:
        max_articles = int(max_articles_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail='Optional "max_articles" must be an integer if provided.',
        )

    language = args.get("language")
    if language is not None and not isinstance(language, str):
        raise HTTPException(
            status_code=400,
            detail='If provided, "language" must be a string.',
        )

    country = args.get("country")
    if country is not None and not isinstance(country, str):
        raise HTTPException(
            status_code=400,
            detail='If provided, "country" must be a string.',
        )

    logger.info(
        "news_sentiment_for_ticker called for ticker=%s max_articles=%s lang=%s country=%s",
        ticker,
        max_articles,
        language,
        country,
    )

    try:
        result = get_news_and_sentiment_for_ticker(
            ticker=ticker,
            max_articles=max_articles,
            language=language,
            country=country,
        )
    except RuntimeError as exc:
        logger.exception("Error while fetching news or computing sentiment")
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return MCPCallResponse(
        tool="news_sentiment_for_ticker",
        ok=True,
        data=result,
    )


@app.post("/mcp/call", response_model=MCPCallResponse)
def call_tool(req: MCPCallRequest) -> MCPCallResponse:
    """
    Generic MCP tool dispatcher.

    The LLM agent client posts a JSON body like:

        {
          "tool": "bq_get_fundamentals",
          "arguments": {
            "ticker": "AAPL",
            "limit": 50
          }
        }

    and receives a structured MCPCallResponse with either data or error.
    """
    tool_name = req.tool

    if tool_name == "bq_get_fundamentals":
        return _handle_bq_get_fundamentals(req.arguments or {})

    if tool_name == "alpha_vantage_get_price_series":
        return _handle_alpha_vantage_get_price_series(req.arguments or {})

    if tool_name == "news_sentiment_for_ticker":
        return _handle_news_sentiment_for_ticker(req.arguments or {})

    raise HTTPException(
        status_code=404,
        detail=f"Unknown tool: {tool_name}",
    )


if __name__ == "__main__":
    # Allow local dev via: python server.py
    import uvicorn

    port_str = os.getenv("PORT", "8080")
    try:
        port = int(port_str)
    except ValueError:
        port = 8080

    uvicorn.run(app, host="0.0.0.0", port=port)
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from bigquery_adapter import get_fundamentals_for_ticker
from alpha_vantage_adapter import get_price_series_for_ticker
from newsdata_adapter import get_news_with_sentiment_for_ticker
from analytics import (
    compute_technical_indicators,
    compute_fundamental_ratios,
    compute_risk_score,
)

# Basic logging configuration. In Cloud Run, logs will be captured by
# Cloud Logging and can be filtered by severity, trace, etc.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("final-mcp-server")

app = FastAPI(
    title="CS530 Final - Agentic Quant MCP Server",
    version="0.3.0",
    description=(
        "MCP server that exposes tools over HTTP for an LLM agent client. "
        "Current focus: BigQuery-based fundamentals, Alpha Vantage prices, "
        "NewsData.io sentiment, and higher-level analysis tools for buy/hold/"
        "sell style narratives."
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

    Performs lightweight checks on configuration. We do not ping
    external services here; any missing configuration will be
    reflected in the "missing_env" field and the status will be
    "degraded" instead of raising an internal error.
    """
    missing: List[str] = []

    # Core GCP config
    if not settings.project_id:
        missing.append("PROJECT_ID")

    if not settings.bq_sec_table_fqn:
        missing.append("BQ_SEC_TABLE_FQN")

    # External APIs - Alpha Vantage and NewsData
    if not getattr(settings, "alpha_vantage_api_key", None):
        missing.append("ALPHA_VANTAGE_API_KEY")

    if not getattr(settings, "newsdata_api_key", None):
        missing.append("NEWSDATA_API_KEY")

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
        MCPTool(
            name="analyze_single_ticker",
            description=(
                "Composite analysis for a single ticker. Combines BigQuery "
                "fundamentals, Alpha Vantage price series, and NewsData.io "
                "sentiment into a single structured snapshot including a "
                "rough risk score."
            ),
            implemented=True,
        ),
        MCPTool(
            name="compare_tickers",
            description=(
                "Compare multiple tickers on the same lookback window using "
                "the composite analysis logic and return a simple ranking by "
                "risk score."
            ),
            implemented=True,
        ),
    ]


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

    # IMPORTANT: never raise 500s here - always return MCPCallResponse
    rows: List[Dict[str, Any]] = []
    error_text: Optional[str] = None

    try:
        rows = get_fundamentals_for_ticker(ticker=ticker, limit=limit)
    except Exception as exc:  # catch everything and surface as MCP error
        logger.exception("Error while fetching fundamentals from BigQuery")
        error_text = str(exc)

    # If BigQuery worked, ok=True and data is populated.
    # If it failed, ok=False and error contains the message.
    return MCPCallResponse(
        tool="bq_get_fundamentals",
        ok=(error_text is None),
        data=(
            {
                "ticker": ticker.upper(),
                "row_count": len(rows),
                "rows": rows,
            }
            if error_text is None
            else None
        ),
        error=error_text,
    )

def _parse_iso_date_str(value: str) -> date:
    """
    Parse a YYYY-MM-DD string into a date, or raise a 400 HTTP error.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format {value!r}. Use YYYY-MM-DD.",
        )

def _handle_alpha_vantage_get_price_series(
    args: Dict[str, Any] | None,
) -> MCPCallResponse:
    """
    Internal handler for the alpha_vantage_get_price_series tool.

    Expected arguments:
    - ticker (str; required): stock ticker symbol.
    - start_date (str; required): YYYY-MM-DD inclusive.
    - end_date (str; required): YYYY-MM-DD inclusive.
    - resolution (str; optional): currently only "D" (daily) is supported.
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
            detail=(
                "alpha_vantage_get_price_series requires a string "
                '"ticker" argument.'
            ),
        )

    start_date_raw = args.get("start_date")
    end_date_raw = args.get("end_date")
    if not isinstance(start_date_raw, str) or not isinstance(end_date_raw, str):
        raise HTTPException(
            status_code=400,
            detail='Both "start_date" and "end_date" must be strings (YYYY-MM-DD).',
        )

    # Parse into date objects for the adapter
    start_date = _parse_iso_date_str(start_date_raw)
    end_date = _parse_iso_date_str(end_date_raw)

    resolution = args.get("resolution", "D")
    if resolution != "D":
        raise HTTPException(
            status_code=400,
            detail='Only daily resolution "D" is supported at this time.',
        )

    logger.info(
        "alpha_vantage_get_price_series called for ticker=%s start=%s end=%s "
        "resolution=%s",
        ticker,
        start_date_raw,
        end_date_raw,
        resolution,
    )

    try:
        points = get_price_series_for_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            # leave max_points as default 60 for now
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
            "start_date": start_date_raw,
            "end_date": end_date_raw,
            "resolution": resolution,
            "point_count": len(points),
            "points": points,
        },
    )


def _handle_news_sentiment_for_ticker(
    args: Dict[str, Any] | None,
) -> MCPCallResponse:
    """
    Internal handler for the news_sentiment_for_ticker tool.

    Expected arguments:
    - ticker (str; required): stock ticker symbol (used as query keyword).
    - max_articles (int; optional): max number of articles to score.
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
            detail=(
                "news_sentiment_for_ticker requires a string "
                '"ticker" argument.'
            ),
        )

    max_articles_raw = args.get("max_articles", 10)
    try:
        max_articles = int(max_articles_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail='Optional "max_articles" must be an integer if provided.',
        )

    logger.info(
        "news_sentiment_for_ticker called for ticker=%s max_articles=%s",
        ticker,
        max_articles,
    )

    try:
        result = get_news_with_sentiment_for_ticker(
            ticker=ticker,
            max_articles=max_articles,
        )
    except RuntimeError as exc:
        logger.exception("Error while fetching news sentiment from NewsData.io")
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return MCPCallResponse(
        tool="news_sentiment_for_ticker",
        ok=True,
        data=result,
    )


def _today_date() -> date:
    # For server side analytics we can simply use local date.
    return date.today()


def _analyze_ticker_internal(
    ticker: str,
    lookback_days: int,
) -> Dict[str, Any]:
    """
    Internal helper that performs the full composite analysis for a
    single ticker using the underlying adapters directly.
    """
    # Price window for Alpha Vantage
    today = _today_date()  # returns a date object
    start_date = today - timedelta(days=lookback_days)
    end_date = today

    # Fundamentals
    fundamentals_block: Dict[str, Any]
    try:
        fund_rows = get_fundamentals_for_ticker(ticker=ticker, limit=500)
        fund_ratios = compute_fundamental_ratios(fund_rows)
        fundamentals_block = {
            "has_data": fund_ratios.get("has_data", False),
            "latest_period": fund_ratios.get("latest_period"),
            "ratios": fund_ratios.get("ratios", {}),
            "row_count": len(fund_rows),
        }
    except RuntimeError as exc:
        fundamentals_block = {
            "error": str(exc),
            "has_data": False,
            "ratios": {},
            "row_count": 0,
        }

    # Prices and technicals
    prices_block: Dict[str, Any]
    technical_block: Dict[str, Any]
    try:
        points = get_price_series_for_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            # use default max_points from the adapter
        )
        technical_block = compute_technical_indicators(points)
        prices_block = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "resolution": "D",
            "point_count": len(points),
            "points": points,
        }
    except RuntimeError as exc:
        technical_block = {
            "has_data": False,
            "error": str(exc),
            "point_count": 0,
        }
        prices_block = {
            "error": str(exc),
        }

    # News and sentiment
    try:
        sentiment_block = get_news_with_sentiment_for_ticker(
            ticker=ticker,
            max_articles=10,
        )
    except RuntimeError as exc:
        sentiment_block = {
            "ticker": ticker.upper(),
            "error": str(exc),
        }

    # Risk score
    risk_block = compute_risk_score(
        technical=technical_block,
        fundamentals=fundamentals_block,
        sentiment=sentiment_block,
    )

    return {
        "ticker": ticker.upper(),
        "fundamentals": fundamentals_block,
        "prices": prices_block,
        "technical": technical_block,
        "sentiment": sentiment_block,
        "risk": risk_block,
    }


def _handle_analyze_single_ticker(
    args: Dict[str, Any] | None,
) -> MCPCallResponse:
    """
    Internal handler for the analyze_single_ticker composite tool.

    Expected arguments:
    - ticker (str; required)
    - lookback_days (int; optional, default 90)
    """
    if args is None:
        raise HTTPException(
            status_code=400,
            detail="analyze_single_ticker requires arguments.",
        )

    ticker = args.get("ticker")
    if not ticker or not isinstance(ticker, str):
        raise HTTPException(
            status_code=400,
            detail='analyze_single_ticker requires a string "ticker" argument.',
        )

    lookback_raw = args.get("lookback_days", 90)
    try:
        lookback_days = int(lookback_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail='Optional "lookback_days" must be an integer if provided.',
        )

    logger.info(
        "analyze_single_ticker called for ticker=%s lookback_days=%s",
        ticker,
        lookback_days,
    )

    snapshot = _analyze_ticker_internal(ticker=ticker, lookback_days=lookback_days)

    return MCPCallResponse(
        tool="analyze_single_ticker",
        ok=True,
        data={
            "ticker": ticker.upper(),
            "lookback_days": lookback_days,
            "snapshot": snapshot,
        },
    )


def _handle_compare_tickers(
    args: Dict[str, Any] | None,
) -> MCPCallResponse:
    """
    Internal handler for the compare_tickers composite tool.

    Expected arguments:
    - tickers (List[str]; required): list of 2 to 5 ticker symbols.
    - lookback_days (int; optional, default 90)
    """
    if args is None:
        raise HTTPException(
            status_code=400,
            detail="compare_tickers requires arguments.",
        )

    raw_tickers = args.get("tickers")
    if not isinstance(raw_tickers, list):
        raise HTTPException(
            status_code=400,
            detail='compare_tickers requires a list "tickers" argument.',
        )

    tickers: List[str] = []
    for item in raw_tickers:
        if isinstance(item, str) and item.strip():
            tickers.append(item.strip().upper())

    if len(tickers) < 2:
        raise HTTPException(
            status_code=400,
            detail="compare_tickers requires at least two tickers.",
        )
    if len(tickers) > 5:
        raise HTTPException(
            status_code=400,
            detail="compare_tickers supports at most five tickers.",
        )

    lookback_raw = args.get("lookback_days", 90)
    try:
        lookback_days = int(lookback_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail='Optional "lookback_days" must be an integer if provided.',
        )

    logger.info(
        "compare_tickers called for tickers=%s lookback_days=%s",
        tickers,
        lookback_days,
    )

    snapshots: List[Dict[str, Any]] = []
    for t in tickers:
        snapshot = _analyze_ticker_internal(ticker=t, lookback_days=lookback_days)
        snapshots.append(snapshot)

    def _risk_score(snap: Dict[str, Any]) -> float:
        risk = snap.get("risk") or {}
        score = risk.get("score")
        try:
            return float(score)
        except (TypeError, ValueError):
            # Treat missing scores as moderate risk.
            return 0.5

    ranked = sorted(snapshots, key=_risk_score)

    ranking_by_risk = [
        {
            "ticker": snap.get("ticker"),
            "risk_score": (snap.get("risk") or {}).get("score"),
            "risk_label": (snap.get("risk") or {}).get("label"),
        }
        for snap in ranked
    ]

    return MCPCallResponse(
        tool="compare_tickers",
        ok=True,
        data={
            "tickers": tickers,
            "lookback_days": lookback_days,
            "snapshots": snapshots,
            "ranking_by_risk": ranking_by_risk,
        },
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

    if tool_name == "analyze_single_ticker":
        return _handle_analyze_single_ticker(req.arguments or {})

    if tool_name == "compare_tickers":
        return _handle_compare_tickers(req.arguments or {})

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
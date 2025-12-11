from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from bigquery_adapter import get_fundamentals_for_ticker
from finnhub_adapter import get_price_series_for_ticker

# Basic logging configuration. In Cloud Run, logs will be captured by
# Cloud Logging and can be filtered by severity, trace, etc.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("final-mcp-server")

app = FastAPI(
    title="CS530 Final - Agentic Quant MCP Server",
    version="0.3.0",
    description=(
        "MCP server that exposes tools over HTTP for an LLM agent client. "
        "Current focus: BigQuery-based fundamentals and (later) finance "
        "and sentiment APIs."
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
            name="finnhub_get_price_series",
            description=(
                "Get historical OHLCV price time series for a ticker from "
                "Finnhub using daily resolution and a start and end date."
            ),
            implemented=True,
        ),
        MCPTool(
            name="news_sentiment_for_ticker",
            description="Fetch recent news for a ticker and attach sentiment scores.",
            implemented=False,
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


def _handle_finnhub_get_price_series(args: Dict[str, Any] | None) -> MCPCallResponse:
    """
    Internal handler for the finnhub_get_price_series tool.

    Expected arguments:
    - ticker (str; required): stock ticker symbol.
    - start_date (str; required): ISO date string YYYY-MM-DD.
    - end_date (str; required): ISO date string YYYY-MM-DD.
    - resolution (str; optional): Finnhub resolution code, default "D".
    """
    if args is None:
        raise HTTPException(
            status_code=400,
            detail="finnhub_get_price_series requires arguments.",
        )

    ticker = args.get("ticker")
    if not ticker or not isinstance(ticker, str):
        raise HTTPException(
            status_code=400,
            detail='finnhub_get_price_series requires a string "ticker" argument.',
        )

    start_date = args.get("start_date")
    end_date = args.get("end_date")
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise HTTPException(
            status_code=400,
            detail=(
                'finnhub_get_price_series requires "start_date" and '
                '"end_date" arguments as YYYY-MM-DD strings.'
            ),
        )

    resolution = args.get("resolution", "D")
    if not isinstance(resolution, str):
        raise HTTPException(
            status_code=400,
            detail='Optional "resolution" must be a string if provided.',
        )

    logger.info(
        "finnhub_get_price_series called for ticker=%s start=%s end=%s resolution=%s",
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
    except ValueError as exc:
        logger.exception("Invalid arguments for finnhub_get_price_series")
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.exception("Error while fetching price series from Finnhub")
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return MCPCallResponse(
        tool="finnhub_get_price_series",
        ok=True,
        data={
            "ticker": ticker.upper(),
            "resolution": resolution,
            "point_count": len(points),
            "points": points,
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

    or:

        {
          "tool": "finnhub_get_price_series",
          "arguments": {
            "ticker": "AAPL",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
          }
        }

    and receives a structured MCPCallResponse with either data or error.
    """
    tool_name = req.tool

    if tool_name == "bq_get_fundamentals":
        return _handle_bq_get_fundamentals(req.arguments or {})

    if tool_name == "finnhub_get_price_series":
        return _handle_finnhub_get_price_series(req.arguments or {})

    # Placeholder for future tools
    if tool_name in {"news_sentiment_for_ticker"}:
        raise HTTPException(
            status_code=400,
            detail=f"Tool {tool_name} is declared but not implemented yet.",
        )

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
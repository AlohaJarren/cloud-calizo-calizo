from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings


app = FastAPI(
    title="CS 530 Final MCP Server: Stock Research Assistant",
    description=(
        "MCP server exposing tools for quant research using "
        "BigQuery public data, Finnhub, and NewsData.io."
    ),
    version="0.1.0",
)


# Pydantic models for MCP-style tools

class ToolDescription(BaseModel):
    """
    Describes a single MCP tool.

    Note: input_schema and output_schema are lightweight JSON Schema-like
    dictionaries so the client agent can reason about arguments and results.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    implemented: bool = Field(
        default=False,
        description="Whether this tool is fully implemented on the server.",
    )


class ToolsListResponse(BaseModel):
    tools: List[ToolDescription]


class ToolCallRequest(BaseModel):
    """
    Generic request wrapper for calling an MCP tool.

    Example:
    {
        "tool_name": "analyze_single_ticker",
        "arguments": {
            "ticker": "AAPL",
            "horizon": "3y"
        }
    }
    """

    tool_name: str = Field(..., description="Name of the tool to call.")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific arguments as a JSON object.",
    )


class ToolCallResponse(BaseModel):
    """
    Generic response wrapper from an MCP tool call.
    """

    tool_name: str
    result: Any

# Tool registry: placeholder definitions

def _build_tool_registry() -> Dict[str, ToolDescription]:
    """
    Build the registry of available tools.
    """

    tools: Dict[str, ToolDescription] = {}

    tools["bq_get_fundamentals"] = ToolDescription(
        name="bq_get_fundamentals",
        description=(
            "Placeholder: will fetch fundamental financial data for a "
            "given ticker from the BigQuery SEC public dataset."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "years": {
                    "type": "integer",
                    "description": "Number of years of history to retrieve",
                },
                "period": {
                    "type": "string",
                    "enum": ["annual", "quarterly"],
                    "description": "Financial reporting period type",
                },
            },
            "required": ["ticker"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "statements": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
        },
        implemented=False,
    )

    tools["get_price_history"] = ToolDescription(
        name="get_price_history",
        description=(
            "Placeholder:  will fetch historical OHLCV price data "
            "for a ticker using the Finnhub API."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO date, e.g. 2020-01-01"},
                "end_date": {"type": "string", "description": "ISO date, e.g. 2024-12-31"},
            },
            "required": ["ticker"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "prices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "open": {"type": "number"},
                            "high": {"type": "number"},
                            "low": {"type": "number"},
                            "close": {"type": "number"},
                            "volume": {"type": "number"},
                        },
                    },
                },
            },
        },
        implemented=False,
    )

    tools["get_news_sentiment"] = ToolDescription(
        name="get_news_sentiment",
        description=(
            "Placeholder:  will fetch recent news articles for a ticker "
            "from NewsData.io and attach basic sentiment labels."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {
                    "type": "integer",
                    "description": "How many days back to search for news",
                },
            },
            "required": ["ticker"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "articles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "headline": {"type": "string"},
                            "source": {"type": "string"},
                            "published_at": {"type": "string"},
                            "sentiment": {"type": "string"},
                        },
                    },
                },
            },
        },
        implemented=False,
    )

    tools["analyze_single_ticker"] = ToolDescription(
        name="analyze_single_ticker",
        description=(
            "Placeholder: high-level tool that will combine fundamentals, "
            "price history, and news sentiment into a single analysis for "
            "one ticker."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "horizon": {
                    "type": "string",
                    "description": "Time horizon string like '1y' or '3y'",
                },
            },
            "required": ["ticker"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "summary": {"type": "string"},
                "risk_band": {"type": "string"},
                "fundamentals": {"type": "object"},
                "technicals": {"type": "object"},
                "sentiment": {"type": "object"},
            },
        },
        implemented=False,
    )

    tools["compare_tickers"] = ToolDescription(
        name="compare_tickers",
        description=(
            "Placeholder: high-level tool that will compare multiple "
            "tickers on fundamentals, technicals, and sentiment."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": "List of ticker symbols to compare",
                },
                "horizon": {
                    "type": "string",
                    "description": "Time horizon string like '1y' or '3y'",
                },
            },
            "required": ["tickers"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "comparison_table": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "ranking": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        implemented=False,
    )

    return tools


TOOL_REGISTRY: Dict[str, ToolDescription] = _build_tool_registry()

# Health and readiness endpoints

@app.get("/healthz")
def healthz() -> Dict[str, str]:
    """
    Basic liveness endpoint.

    Use this for simple container health checks (Cloud Run, docker).
    """
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> Dict[str, Any]:
    """
    Readiness endpoint.

    For now this just returns some lightweight config info.
    Later, you can extend this to check connectivity to
    BigQuery and external APIs.
    """
    return {
        "status": "ready",
        "project_id": settings.project_id or "(unset)",
        "environment": settings.environment,
    }


# MCP endpoints

@app.post("/mcp/tools/list", response_model=ToolsListResponse)
def list_tools() -> ToolsListResponse:
    """
    Return the list of MCP tools exposed by this server.

    In MCP terms, this is similar to the "tools/list" request.
    """
    return ToolsListResponse(tools=list(TOOL_REGISTRY.values()))


@app.post("/mcp/tools/call", response_model=ToolCallResponse)
def call_tool(request: ToolCallRequest) -> ToolCallResponse:
    """
    Invoke a specific MCP tool by name.

    In this first commit, all tools are placeholders and will return
    a 501 Not Implemented response so that the client agent can still
    exercise the protocol and error handling.
    """
    tool_name = request.tool_name

    if tool_name not in TOOL_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown tool '{tool_name}'. Known tools: {list(TOOL_REGISTRY.keys())}",
        )

    # Placeholder behavior: tools are advertised but not implemented yet.
    raise HTTPException(
        status_code=501,
        detail=f"Tool '{tool_name}' is not implemented yet on the server.",
    )


# Local development entrypoint

if __name__ == "__main__":
    # Allow running with: python server.py
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),  # type: ignore[name-defined]
        reload=True,
    )
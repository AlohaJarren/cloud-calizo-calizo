from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

# Base URL for the MCP server. In Cloud Run this will be your deployed URL,
# for local dev it defaults to the FastAPI instance on 8080.
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")


@dataclass
class MCPResult:
    tool: str
    ok: bool
    data: Any
    error: Optional[str] = None


def _call_mcp_tool(tool: str, arguments: Dict[str, Any]) -> MCPResult:
    """
    Low-level helper to call the MCP server's /mcp/call endpoint.

    This is a thin wrapper over HTTP that handles both successful
    MCPCallResponse objects and FastAPI error responses.
    """
    url = f"{MCP_SERVER_URL}/mcp/call"

    try:
        resp = httpx.post(
            url,
            json={"tool": tool, "arguments": arguments},
            timeout=20.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return MCPResult(
            tool=tool,
            ok=False,
            data=None,
            error=f"HTTP error calling MCP tool {tool}: {exc}",
        )

    payload = resp.json()

    # When the FastAPI handler raises HTTPException, the shape is {"detail": "..."}.
    if "detail" in payload and "ok" not in payload:
        return MCPResult(
            tool=tool,
            ok=False,
            data=None,
            error=str(payload["detail"]),
        )

    # Normal MCPCallResponse shape:
    #   { "tool": "...", "ok": true/false, "data": ..., "error": "..." }
    return MCPResult(
        tool=str(payload.get("tool", tool)),
        ok=bool(payload.get("ok", False)),
        data=payload.get("data"),
        error=payload.get("error"),
    )


def _today_utc() -> date:
    """
    Convenience helper to get today's date.

    The Alpha Vantage free tier is daily bars with a recent window, so we
    just need a reasonable recent range; we do not need exact market close
    alignment here.
    """
    return datetime.now(timezone.utc).date()


def _summarize_price_trend(price_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce a small heuristic summary of price action.

    This is a simple numeric "agent" layer on top of the raw OHLCV series.
    """
    points: List[Dict[str, Any]] = price_data.get("points") or []
    if len(points) < 2:
        return {
            "has_data": False,
            "message": "Not enough price data points to compute trend.",
        }

    closes = [float(p["close"]) for p in points]
    first = closes[0]
    last = closes[-1]
    change = last - first
    pct = (change / first * 100.0) if first else 0.0

    if pct > 5.0:
        label = "uptrend"
    elif pct < -5.0:
        label = "downtrend"
    else:
        label = "sideways"

    return {
        "has_data": True,
        "days": len(points),
        "first_close": first,
        "last_close": last,
        "absolute_change": change,
        "percent_change": pct,
        "trend_label": label,
    }


def _summarize_fundamentals(fund_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightly summarize BigQuery fundamentals rows.

    The BigQuery schema can be complex, so we avoid hard-coding column names.
    Instead we expose counts and show a small sample that an LLM or human
    can reason about later.
    """
    rows: List[Dict[str, Any]] = fund_data.get("rows") or []
    row_count = int(fund_data.get("row_count", len(rows)))

    sample_rows = rows[:3]

    return {
        "row_count": row_count,
        "sample_rows": sample_rows,
    }


def _summarize_news_sentiment(news_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Thin wrapper around the NewsData-based sentiment output.

    This keeps the client side logic simple and lets the MCP server own
    the details of the scoring.
    """
    return {
        "article_count": int(news_data.get("article_count", 0)),
        "average_score": float(news_data.get("average_score", 0.0)),
        "aggregate_label": news_data.get("aggregate_label", "neutral"),
        "articles": news_data.get("articles") or [],
    }


def run_quant_research_session(
    ticker: str,
    lookback_days: int = 30,
    max_news: int = 10,
) -> None:
    """
    Agent-like orchestration for a single ticker.

    This function composes three MCP tools:
      - bq_get_fundamentals: SEC fundamentals via BigQuery public data.
      - alpha_vantage_get_price_series: recent daily OHLCV prices.
      - news_sentiment_for_ticker: recent news with lexical sentiment.

    The output is a combined "research snapshot" printed to stdout.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        print("[client] Ticker must be a non-empty string.", file=sys.stderr)
        return

    print(f"=== Quant Research Session for {ticker} ===")
    print(f"MCP server base URL: {MCP_SERVER_URL}")
    print()

    # 1) Fundamentals via BigQuery
    print("[1/3] Fetching fundamentals from BigQuery via MCP...")
    fundamentals_result = _call_mcp_tool(
        "bq_get_fundamentals",
        {"ticker": ticker, "limit": 64},
    )
    if not fundamentals_result.ok:
        print(f"  - Error: {fundamentals_result.error}", file=sys.stderr)
        basics: Dict[str, Any] = {
            "fundamentals": {"error": fundamentals_result.error}
        }
    else:
        fundamental_summary = _summarize_fundamentals(
            fundamentals_result.data or {}
        )
        basics = {"fundamentals": fundamental_summary}
        print(
            f"  - Rows available: {fundamental_summary['row_count']} "
            f"(showing up to 3 sample rows)."
        )

    print()

    # 2) Recent price action via Alpha Vantage
    print("[2/3] Fetching recent price series via MCP...")
    end = _today_utc()
    start = end - timedelta(days=lookback_days)
    price_result = _call_mcp_tool(
        "alpha_vantage_get_price_series",
        {
            "ticker": ticker,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    if not price_result.ok:
        print(f"  - Error: {price_result.error}", file=sys.stderr)
        basics["price_trend"] = {"error": price_result.error}
    else:
        trend_summary = _summarize_price_trend(price_result.data or {})
        basics["price_trend"] = trend_summary
        if trend_summary.get("has_data"):
            print(
                "  - Trend over last {days} trading days: {label} "
                "(change {pct:.2f}% from {first:.2f} to {last:.2f})".format(
                    days=trend_summary["days"],
                    label=trend_summary["trend_label"],
                    pct=trend_summary["percent_change"],
                    first=trend_summary["first_close"],
                    last=trend_summary["last_close"],
                )
            )
        else:
            print("  - Not enough price data to compute trend.")

    print()

    # 3) News sentiment via NewsData
    print("[3/3] Fetching news and sentiment via MCP...")
    news_result = _call_mcp_tool(
        "news_sentiment_for_ticker",
        {
            "ticker": ticker,
            "max_articles": max_news,
        },
    )
    if not news_result.ok:
        print(f"  - Error: {news_result.error}", file=sys.stderr)
        basics["news_sentiment"] = {"error": news_result.error}
        sentiment_summary: Dict[str, Any] = {}
    else:
        sentiment_summary = _summarize_news_sentiment(news_result.data or {})
        basics["news_sentiment"] = {
            "article_count": sentiment_summary["article_count"],
            "average_score": sentiment_summary["average_score"],
            "aggregate_label": sentiment_summary["aggregate_label"],
        }
        print(
            "  - News sentiment: {label} "
            "(avg score {score:.2f} across {count} articles)".format(
                label=sentiment_summary["aggregate_label"],
                score=sentiment_summary["average_score"],
                count=sentiment_summary["article_count"],
            )
        )

    print()
    print("=== Combined Research Snapshot (JSON) ===")
    print(
        json.dumps(
            {
                "ticker": ticker,
                "lookback_days": lookback_days,
                "snapshot": basics,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )

    # Optionally show a tiny peek at the first news headlines so the
    # screencast demonstrates cross-tool context.
    news_block = basics.get("news_sentiment", {})
    if "error" not in news_block and sentiment_summary:
        print()
        print("Sample news headlines:")
        articles = sentiment_summary["articles"]
        for idx, art in enumerate(articles[:3], start=1):
            title = art.get("title") or "(no title)"
            lbl = art.get("sentiment_label", "neutral")
            print(f"  {idx}. [{lbl}] {title}")


def run_analyze_single_ticker_session(
    ticker: str,
    lookback_days: int = 90,
) -> None:
    """
    Use the composite analyze_single_ticker MCP tool for one ticker.

    This hits the server-side orchestration that combines fundamentals,
    prices, sentiment, and a simple risk score into one snapshot.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        print("[client] Ticker must be a non-empty string.", file=sys.stderr)
        return

    print(f"=== Composite Analysis for {ticker} ===")
    print(f"MCP server base URL: {MCP_SERVER_URL}")
    print(f"Lookback window: {lookback_days} days")
    print()

    result = _call_mcp_tool(
        "analyze_single_ticker",
        {
            "ticker": ticker,
            "lookback_days": lookback_days,
        },
    )
    if not result.ok:
        print(f"[client] Error from analyze_single_ticker: {result.error}", file=sys.stderr)
        return

    payload = result.data or {}
    # Server response shape:
    # {
    #   "ticker": "...",
    #   "lookback_days": ...,
    #   "snapshot": { ... }
    # }
    snapshot = payload.get("snapshot") or payload

    risk_block = snapshot.get("risk") or {}
    fundamentals_block = snapshot.get("fundamentals") or {}
    technical_block = snapshot.get("technical") or {}
    sentiment_block = snapshot.get("sentiment") or {}

    score = risk_block.get("score")
    label = risk_block.get("label", "unknown")

    print("Risk summary:")
    if score is not None:
        try:
            score_float = float(score)
        except (TypeError, ValueError):
            score_float = None
        if score_float is not None:
            print(f"  - Risk label: {label} (score ~{score_float:.2f} on [0,1])")
        else:
            print(f"  - Risk label: {label} (score unavailable)")
    else:
        print(f"  - Risk label: {label} (score unavailable)")

    print()
    print("Fundamentals summary:")
    print(f"  - Has data: {fundamentals_block.get('has_data', False)}")
    print(f"  - Row count: {fundamentals_block.get('row_count')}")

    print()
    print("Technical summary:")
    print(f"  - Has data: {technical_block.get('has_data', False)}")
    print(f"  - Latest date: {technical_block.get('latest_date')}")
    print(f"  - Latest close: {technical_block.get('latest_close')}")
    print(f"  - Total change %: {technical_block.get('change_pct_total')}")
    print(f"  - Trend label: {technical_block.get('trend_label')}")

    print()
    print("Sentiment summary:")
    print(f"  - Aggregate label: {sentiment_block.get('aggregate_label')}")
    print(f"  - Article count: {sentiment_block.get('article_count')}")

    print()
    print("=== Raw composite snapshot (JSON) ===")
    print(json.dumps(payload, indent=2, default=str))


def run_compare_tickers_session(
    tickers: List[str],
    lookback_days: int = 30,
) -> None:
    """
    Compare multiple tickers using the compare_tickers MCP tool.

    The server returns a ranking by risk score along with full snapshots
    for each ticker. We print a compact ranking for the screencast and
    then dump the JSON so you can scroll through it.
    """
    cleaned = [t.upper().strip() for t in tickers if t.strip()]
    if len(cleaned) < 2:
        print("[client] Need at least two tickers to compare.", file=sys.stderr)
        return

    print("=== Multi-ticker risk comparison ===")
    print(f"MCP server base URL: {MCP_SERVER_URL}")
    print(f"Tickers: {', '.join(cleaned)}")
    print(f"Lookback window: {lookback_days} days")
    print()

    result = _call_mcp_tool(
        "compare_tickers",
        {
            "tickers": cleaned,
            "lookback_days": lookback_days,
        },
    )
    if not result.ok:
        print(f"[client] Error from compare_tickers: {result.error}", file=sys.stderr)
        return

    data = result.data or {}
    ranking = data.get("ranking_by_risk") or []

    if not ranking:
        print("[client] No ranking returned from compare_tickers.")
    else:
        print("Ranking from lowest to highest risk:")
        for idx, entry in enumerate(ranking, start=1):
            t = entry.get("ticker") or "?"
            score = entry.get("risk_score")
            label = entry.get("risk_label", "unknown")
            if isinstance(score, (int, float)):
                print(f"  {idx}. {t}: {label} (score ~{score:.2f})")
            else:
                print(f"  {idx}. {t}: {label} (score unavailable)")

    print()
    print("=== Raw compare_tickers result (JSON) ===")
    print(json.dumps(data, indent=2, default=str))


def main(argv: List[str]) -> None:
    """
    Simple CLI entrypoint.

    Usage patterns:
      - python client.py
            Prompts for an interactive mode and ticker(s).

      - python client.py ticker AAPL
            Runs a single-ticker research session for AAPL.

      - python client.py ticker AAPL 60
            Uses a 60 day lookback window instead of the default 30.

      - python client.py analyze AAPL 90
            Uses the composite analyze_single_ticker tool for AAPL.

      - python client.py compare AAPL MSFT NVDA 45
            Compares AAPL, MSFT, and NVDA over a 45 day lookback window.
    """
    # CLI subcommand: single-ticker 3-tool flow (original behavior)
    if len(argv) >= 3 and argv[1] == "ticker":
        ticker = argv[2]
        if len(argv) >= 4:
            try:
                lookback = int(argv[3])
            except ValueError:
                print(
                    "[client] Invalid lookback_days argument; using default 30.",
                    file=sys.stderr,
                )
                lookback = 30
        else:
            lookback = 30

        run_quant_research_session(ticker=ticker, lookback_days=lookback)
        return

    # CLI subcommand: composite analysis
    if len(argv) >= 3 and argv[1] == "analyze":
        ticker = argv[2]
        if len(argv) >= 4:
            try:
                lookback = int(argv[3])
            except ValueError:
                print(
                    "[client] Invalid lookback_days argument; using default 90.",
                    file=sys.stderr,
                )
                lookback = 90
        else:
            lookback = 90

        run_analyze_single_ticker_session(ticker=ticker, lookback_days=lookback)
        return

    # CLI subcommand: multi-ticker comparison
    if len(argv) >= 4 and argv[1] == "compare":
        raw_args = argv[2:]
        lookback = 30

        # Allow optional trailing integer for lookback_days
        if raw_args:
            try:
                maybe_lookback = int(raw_args[-1])
                lookback = maybe_lookback
                ticker_args = raw_args[:-1]
            except ValueError:
                ticker_args = raw_args
        else:
            ticker_args = []

        run_compare_tickers_session(
            tickers=ticker_args,
            lookback_days=lookback,
        )
        return

    # Interactive mode if no subcommand is provided
    print("Agentic Quant Research Client")
    print("------------------------------")
    print("Choose an option:")
    print("  1) Single ticker snapshot (fundamentals + prices + news)")
    print("  2) Compare multiple tickers by risk score")
    print("  3) Single ticker composite analysis with risk score")
    choice = input("Enter choice [1-3] (default 1): ").strip() or "1"

    if choice == "2":
        tickers_str = input(
            "Enter ticker symbols separated by commas (e.g., AAPL, MSFT, GOOG): "
        ).strip()
        if not tickers_str:
            print("[client] No tickers entered; aborting.", file=sys.stderr)
            return
        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        if len(tickers) < 2:
            print("[client] Need at least two tickers for comparison.", file=sys.stderr)
            return
        run_compare_tickers_session(tickers=tickers, lookback_days=30)
        return

    if choice == "3":
        ticker = input("Enter ticker symbol (e.g., AAPL): ").strip()
        if not ticker:
            print("[client] No ticker entered; aborting.", file=sys.stderr)
            return
        run_analyze_single_ticker_session(ticker=ticker, lookback_days=90)
        return

    # Default: single-ticker 3-tool flow
    ticker = input("Enter ticker symbol (e.g., AAPL): ").strip()
    if not ticker:
        print("[client] No ticker entered; aborting.", file=sys.stderr)
        return
    run_quant_research_session(ticker=ticker, lookback_days=30)


if __name__ == "__main__":
    main(sys.argv)
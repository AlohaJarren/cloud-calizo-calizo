from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
        resp = httpx.post(url, json={"tool": tool, "arguments": arguments}, timeout=20.0)
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
    return datetime.utcnow().date()


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


def summarize_with_llm(snapshot: Dict[str, Any], *, ticker: str, mode: str) -> Optional[str]:
    """
    Optional helper that asks an LLM to summarize a single-ticker snapshot.

    The call is gated on the OPENAI_API_KEY env var so that the project
    still runs fine without any LLM credentials configured.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[client] OPENAI_API_KEY not set; skipping LLM summary.", file=sys.stderr)
        return None

    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        print(
            "[client] openai package not installed; run 'pip install openai' to enable LLM summaries.",
            file=sys.stderr,
        )
        return None

    client = OpenAI()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system_msg = (
        "You are an educational quantitative research assistant. "
        "Given JSON data about one stock's fundamentals, price action, "
        "technical summary, news sentiment, and a coarse risk score, "
        "write a concise, cautious, plain-English summary for a student. "
        "Always include a clear disclaimer that this is not financial advice."
    )

    user_msg = (
        f"Mode: {mode}\n"
        f"Ticker: {ticker}\n"
        "Here is the JSON snapshot to summarize:\n"
        f"{json.dumps(snapshot, indent=2)}"
    )

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.35,
            max_tokens=500,
        )
    except Exception as exc:
        print(f"[client] LLM summary call failed: {exc}", file=sys.stderr)
        return None

    content = resp.choices[0].message.content
    return content if isinstance(content, str) else str(content)


def run_quant_research_session(
    ticker: str,
    lookback_days: int = 30,
    max_news: int = 10,
    with_llm: bool = True,
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
        basics: Dict[str, Any] = {"fundamentals": {"error": fundamentals_result.error}}
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
    snapshot_payload = {
        "ticker": ticker,
        "lookback_days": lookback_days,
        "snapshot": basics,
    }
    print(
        json.dumps(
            snapshot_payload,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )

    # Optionally show a tiny peek at the first news headlines so the
    # screencast demonstrates cross-tool context.
    news_block = basics.get("news_sentiment", {})
    if sentiment_summary and "error" not in news_block:
        print()
        print("Sample news headlines:")
        articles = sentiment_summary.get("articles") or []
        for idx, art in enumerate(articles[:3], start=1):
            title = art.get("title") or "(no title)"
            lbl = art.get("sentiment_label", "neutral")
            print(f"  {idx}. [{lbl}] {title}")

    if with_llm:
        summary_text = summarize_with_llm(
            snapshot=snapshot_payload,
            ticker=ticker,
            mode="single_ticker_snapshot",
        )
        if summary_text:
            print()
            print("=== LLM Commentary (educational only, not financial advice) ===")
            print(summary_text)


def run_multi_ticker_compare(tickers: List[str], lookback_days: int = 30) -> None:
    """
    Call the compare_tickers MCP tool and pretty-print the ranking.
    """
    symbols = [t.strip().upper() for t in tickers if t.strip()]
    if not symbols:
        print("[client] No tickers provided for comparison.", file=sys.stderr)
        return

    print("=== Multi-ticker risk comparison ===")
    print(f"MCP server base URL: {MCP_SERVER_URL}")
    print("Tickers: " + ", ".join(symbols))
    print(f"Lookback window: {lookback_days} days")
    print()

    result = _call_mcp_tool(
        "compare_tickers",
        {
            "tickers": symbols,
            "lookback_days": lookback_days,
        },
    )
    if not result.ok:
        print(f"[client] Error from MCP tool compare_tickers: {result.error}", file=sys.stderr)
        return

    payload = result.data or {}
    ranking = payload.get("ranking_by_risk") or []

    print("Ranking from lowest to highest risk:")
    for idx, entry in enumerate(ranking, start=1):
        t = entry.get("ticker", "UNKNOWN")
        score = float(entry.get("risk_score", 0.0))
        label = entry.get("risk_label", "unknown")
        print(f"  {idx}. {t}: {label} (score ~{score:.2f})")

    print()
    print("=== Raw compare_tickers result (JSON) ===")
    print(json.dumps(payload, indent=2, sort_keys=False, default=str))


def run_single_ticker_composite(ticker: str, lookback_days: int = 90, with_llm: bool = True) -> None:
    """
    Fetch and display a richer composite snapshot, including risk score.

    This uses the analyze_single_ticker MCP tool on the server, which already
    bundles fundamentals, technicals, sentiment, and a coarse risk score.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        print("[client] Ticker must be a non-empty string.", file=sys.stderr)
        return

    print(f"=== Composite Analysis for {ticker} ===")
    print(f"MCP server base URL: {MCP_SERVER_URL}")
    print(f"Lookback window: {lookback_days} days")
    print()

    # NOTE: call the existing composite tool implemented on the server.
    result = _call_mcp_tool(
        "analyze_single_ticker",
        {
            "ticker": ticker,
            "lookback_days": lookback_days,
        },
    )
    if not result.ok:
        print(f"[client] Error from MCP tool get_composite_snapshot: {result.error}", file=sys.stderr)
        return

    snapshot = result.data or {}
    inner = snapshot.get("snapshot") or {}

    risk = inner.get("risk") or {}
    fundamentals = inner.get("fundamentals") or {}
    technical = inner.get("technical") or {}
    sentiment = inner.get("sentiment") or {}

    print("Risk summary:")
    print(
        "  - Risk label: {label} (score ~{score:.2f} on [0,1])".format(
            label=risk.get("label", "unknown"),
            score=float(risk.get("score", 0.0)),
        )
    )
    print()

    print("Fundamentals summary:")
    print(f"  - Has data: {fundamentals.get('has_data', False)}")
    print(f"  - Row count: {fundamentals.get('row_count', 0)}")
    print()

    print("Technical summary:")
    print(f"  - Has data: {technical.get('has_data', False)}")
    print(f"  - Latest date: {technical.get('latest_date')}")
    print(f"  - Latest close: {technical.get('latest_close')}")
    print(f"  - Total change %: {technical.get('change_pct_total')}")
    print(f"  - Trend label: {technical.get('trend_label')}")
    print()

    print("Sentiment summary:")
    print(f"  - Aggregate label: {sentiment.get('aggregate_label', 'unknown')}")
    print(f"  - Article count: {sentiment.get('article_count', 0)}")
    print()

    print("=== Raw composite snapshot (JSON) ===")
    print(json.dumps(snapshot, indent=2, sort_keys=False, default=str))

    if with_llm:
        summary_text = summarize_with_llm(
            snapshot=snapshot,
            ticker=ticker,
            mode="composite_snapshot",
        )
        if summary_text:
            print()
            print("=== LLM Commentary (educational only, not financial advice) ===")
            print(summary_text)


def main(argv: List[str]) -> None:
    """
    Simple CLI entrypoint.

    Usage patterns:
      - python client.py
            Interactive menu.
      - python client.py ticker AAPL
            Runs a research session for AAPL.
      - python client.py ticker AAPL 60
            Uses a 60 day lookback window instead of the default 30.
      - python client.py compare AAPL MSFT NVDA
            Compares tickers by risk score over the default 30 day window.
    """
    # CLI shortcuts first.
    if len(argv) >= 3 and argv[1] == "compare":
        run_multi_ticker_compare(argv[2:])
        return

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

    # Interactive menu.
    print("Agentic Quant Research Client")
    print("------------------------------")
    print("Choose an option:")
    print("  1) Single ticker snapshot (fundamentals + prices + news)")
    print("  2) Compare multiple tickers by risk score")
    print("  3) Single ticker composite analysis with risk score")
    choice = input("Enter choice [1-3] (default 1): ").strip()

    if choice == "2":
        raw = input("Enter comma-separated tickers (e.g., AAPL,MSFT,NVDA): ").strip()
        if not raw:
            print("[client] No tickers entered; aborting.", file=sys.stderr)
            return
        tickers = [part.strip().upper() for part in raw.split(",") if part.strip()]
        if not tickers:
            print("[client] No valid tickers parsed; aborting.", file=sys.stderr)
            return
        run_multi_ticker_compare(tickers)
    elif choice == "3":
        ticker = input("Enter ticker symbol (e.g., AAPL): ").strip()
        if not ticker:
            print("[client] No ticker entered; aborting.", file=sys.stderr)
            return
        run_single_ticker_composite(ticker=ticker)
    else:
        ticker = input("Enter ticker symbol (e.g., AAPL): ").strip()
        if not ticker:
            print("[client] No ticker entered; aborting.", file=sys.stderr)
            return
        run_quant_research_session(ticker=ticker)


if __name__ == "__main__":
    main(sys.argv)
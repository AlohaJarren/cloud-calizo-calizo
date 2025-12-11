from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from config import settings

NEWSDATA_BASE_URL = "https://newsdata.io/api/1/news"


@dataclass
class NewsArticleSentiment:
    title: str
    description: Optional[str]
    link: Optional[str]
    pub_date: Optional[str]
    source_id: Optional[str]
    sentiment_score: float
    sentiment_label: str


_POSITIVE_WORDS = {
    "beat",
    "beats",
    "growth",
    "surge",
    "record",
    "optimistic",
    "upgrade",
    "bullish",
    "rally",
    "strong",
    "outperform",
    "gain",
    "gains",
    "profits",
}

_NEGATIVE_WORDS = {
    "miss",
    "misses",
    "loss",
    "losses",
    "downgrade",
    "bearish",
    "slump",
    "fall",
    "falls",
    "plunge",
    "weak",
    "lawsuit",
    "fraud",
    "scandal",
    "decline",
}


def _score_text(text: str) -> float:
    """
    Very simple lexical sentiment scorer.

    Counts occurrences of a small set of positive and negative keywords in the
    text and returns a score in [-1.0, 1.0]. This is intentionally lightweight
    so that the LLM agent can still provide the deeper narrative.
    """
    if not text:
        return 0.0

    lowered = text.lower()
    pos_hits = sum(lowered.count(word) for word in _POSITIVE_WORDS)
    neg_hits = sum(lowered.count(word) for word in _NEGATIVE_WORDS)

    total_hits = pos_hits + neg_hits
    if total_hits == 0:
        return 0.0

    raw = (pos_hits - neg_hits) / float(total_hits)
    # Clamp to [-1, 1] just in case
    if raw > 1.0:
        return 1.0
    if raw < -1.0:
        return -1.0
    return raw


def _label_from_score(score: float) -> str:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"


def get_news_and_sentiment_for_ticker(
    ticker: str,
    max_articles: int = 10,
    language: Optional[str] = None,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch recent news for a given ticker/keyword from NewsData.io and attach
    a naive sentiment score for each article, plus an aggregate summary.

    Parameters
    ----------
    ticker : str
        Ticker or keyword to search for (e.g., "AAPL" or "Apple").
    max_articles : int
        Maximum number of articles to process (default 10).
    language : Optional[str]
        Optional ISO language code, e.g. "en".
    country : Optional[str]
        Optional ISO country code for news sources, e.g. "us".

    Returns
    -------
    Dict[str, Any]
        A dictionary containing per-article sentiment and aggregate metrics.
    """
    api_key = settings.newsdata_api_key
    if not api_key:
        raise RuntimeError(
            "NewsData API key not configured. "
            "Set NEWSDATA_API_KEY in the environment."
        )

    params: Dict[str, Any] = {
        "apikey": api_key,
        "q": ticker,
        "category": "business",
    }
    if language:
        params["language"] = language
    if country:
        params["country"] = country

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(NEWSDATA_BASE_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"NewsData HTTP request failed: {exc}") from exc

    data = resp.json()

    status = data.get("status")
    if status != "success":
        message = data.get("message") or data.get("results")
        raise RuntimeError(
            f"NewsData API returned non-success status: {status!r} {message!r}"
        )

    raw_results: List[Dict[str, Any]] = data.get("results") or []
    if not isinstance(raw_results, list):
        raise RuntimeError("NewsData API response missing 'results' list.")

    trimmed = raw_results[: max(0, max_articles)]

    articles: List[NewsArticleSentiment] = []
    scores: List[float] = []

    for item in trimmed:
        title = item.get("title") or ""
        description = item.get("description")
        link = item.get("link")
        pub_date = item.get("pubDate")
        source_id = item.get("source_id")

        combined_text = title
        if description:
            combined_text += " " + description

        score = _score_text(combined_text)
        label = _label_from_score(score)

        scores.append(score)
        articles.append(
            NewsArticleSentiment(
                title=title,
                description=description,
                link=link,
                pub_date=pub_date,
                source_id=source_id,
                sentiment_score=score,
                sentiment_label=label,
            )
        )

    if scores:
        avg_score = sum(scores) / float(len(scores))
    else:
        avg_score = 0.0

    aggregate_label = _label_from_score(avg_score)

    return {
        "ticker": ticker.upper(),
        "article_count": len(articles),
        "average_score": avg_score,
        "aggregate_label": aggregate_label,
        "articles": [
            {
                "title": a.title,
                "description": a.description,
                "link": a.link,
                "pubDate": a.pub_date,
                "source_id": a.source_id,
                "sentiment_score": a.sentiment_score,
                "sentiment_label": a.sentiment_label,
            }
            for a in articles
        ],
    }


def get_news_with_sentiment_for_ticker(
    ticker: str,
    max_articles: int = 10,
    language: Optional[str] = None,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Backwards compatible alias for get_news_and_sentiment_for_ticker.

    The server expects get_news_with_sentiment_for_ticker, so we keep this
    thin wrapper that forwards arguments unchanged.
    """
    return get_news_and_sentiment_for_ticker(
        ticker=ticker,
        max_articles=max_articles,
        language=language,
        country=country,
    )
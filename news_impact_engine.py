import os
import json
import urllib.request
from datetime import datetime, timezone

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")

BEARISH_TERMS = [
    ("hawkish", 15), ("rate hike", 20), ("higher for longer", 20),
    ("inflation hot", 20), ("cpi hotter", 20), ("ppi hotter", 18),
    ("yields rise", 15), ("yield spike", 18), ("treasury yields jump", 18),
    ("tariff", 15), ("war", 15), ("missile", 15), ("geopolitical", 12),
    ("downgrade", 10), ("guidance cut", 15), ("recession", 20),
    ("default", 20), ("shutdown", 12), ("selloff", 10)
]

BULLISH_TERMS = [
    ("dovish", 15), ("rate cut", 20), ("cuts expected", 18),
    ("inflation cools", 20), ("cpi cooler", 20), ("ppi cooler", 18),
    ("yields fall", 15), ("yield drop", 18), ("treasury yields fall", 18),
    ("upgrade", 10), ("guidance raised", 15), ("soft landing", 15),
    ("stimulus", 15), ("ceasefire", 15), ("deal reached", 12),
    ("rally", 8)
]

MACRO_TERMS = [
    "fed", "powell", "fomc", "cpi", "ppi", "jobs", "payrolls",
    "unemployment", "treasury", "yield", "oil", "dollar",
    "tariff", "china", "war", "inflation", "recession", "gdp"
]

WATCH_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "MSFT", "TSLA", "META", "AMZN"]


def fetch_massive_benzinga_news():
    if not MASSIVE_API_KEY:
        return []

    url = (
        "https://api.massive.com/benzinga/v2/news"
        "?limit=30"
        "&sort=published.desc"
        f"&apiKey={MASSIVE_API_KEY}"
    )

    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode())

    rows = data.get("results", [])
    rows = rows if isinstance(rows, list) else []
    return rows[:30]


def article_text(row):
    # Score title and teaser only. Avoid full body/transcript noise.
    parts = []
    for key in ["title", "teaser"]:
        val = row.get(key)
        if isinstance(val, str):
            parts.append(val)
    return " ".join(parts)


def is_transcript_or_low_signal(title):
    t = str(title or "").lower()
    bad = [
        "full transcript",
        "earnings call transcript",
        "q1 2027 earnings call",
        "q2 2027 earnings call",
        "q3 2027 earnings call",
        "q4 2027 earnings call",
        "travel infrastructure layer",
    ]
    return any(x in t for x in bad)


def score_article(row):
    title = row.get("title") or row.get("headline") or ""

    if is_transcript_or_low_signal(title):
        return {
            "headline": title,
            "published": row.get("published"),
            "bias": "Neutral",
            "score": 0,
            "impact": 0,
            "tags": [],
            "macro_hits": [],
            "tickers": [],
            "market_relevant": False,
            "ignored": "low_signal_or_transcript",
        }

    text = article_text(row).lower()

    tickers = row.get("tickers") or row.get("stocks") or []
    if not isinstance(tickers, list):
        tickers = []

    watched = [str(x).upper() for x in tickers if str(x).upper() in WATCH_TICKERS]

    macro_hits = [x for x in MACRO_TERMS if x in text]

    hard_macro_terms = [
        "fed", "powell", "fomc", "cpi", "ppi", "payrolls",
        "unemployment", "treasury", "yield", "inflation",
        "oil", "dollar", "tariff", "china", "iran", "recession"
    ]

    hard_macro = any(x in text for x in hard_macro_terms)
    market_relevant = bool(hard_macro or watched)

    score = 0
    tags = []

    if market_relevant:
        for term, weight in BEARISH_TERMS:
            if term in text:
                # Require geopolitical terms to be tied to true macro context.
                if term in ["war", "missile", "geopolitical"]:
                    if not any(x in text for x in ["oil", "iran", "china", "israel", "russia", "tariff", "treasury", "yield"]):
                        continue
                score -= weight
                tags.append(term)

        for term, weight in BULLISH_TERMS:
            if term in text:
                score += weight
                tags.append(term)

    # Specific macro adjustments
    if "oil" in text and any(x in text for x in ["iran", "strait of hormuz", "war", "missile"]):
        score -= 10
        tags.append("oil/geopolitical risk")

    if "ceasefire" in text or "deal reached" in text:
        score += 10
        tags.append("de-escalation")

    if "rally" in tags and score < 0:
        # Don't let a bullish risk-asset rally headline stay too bearish unless macro shock dominates.
        score += 8

    impact = min(10, len(macro_hits) + len(watched) + min(10, abs(score)) // 5)

    if not market_relevant:
        score = 0
        impact = 0
        bias = "Neutral"
    elif score > 0:
        bias = "Bullish"
    elif score < 0:
        bias = "Bearish"
    else:
        bias = "Neutral"

    return {
        "headline": title,
        "published": row.get("published"),
        "bias": bias,
        "score": score,
        "impact": impact,
        "tags": tags[:8],
        "macro_hits": macro_hits[:8],
        "tickers": watched[:8],
        "market_relevant": market_relevant,
    }

def news_impact(headlines=None):
    source = "manual"

    if headlines is not None:
        rows = [{"title": h} for h in headlines]
    else:
        rows = []
        source = "massive_benzinga"
        try:
            rows = fetch_massive_benzinga_news()
        except Exception as e:
            return {
                "service": "execution_service",
                "module": "news_impact_engine_v3",
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                "available": False,
                "source": "massive_benzinga_error",
                "news_bias": "Neutral",
                "news_score": 0,
                "severity": "LOW",
                "headline_count": 0,
                "top_headlines": [],
                "note": str(e),
            }

    seen = set()
    scored = []
    for row in rows:
        item = score_article(row)
        key = item.get("headline", "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if item.get("impact", 0) <= 0 and not item.get("market_relevant"):
            continue
        scored.append(item)

    scored = sorted(scored, key=lambda x: (x["impact"], abs(x["score"])), reverse=True)

    # Cap extreme aggregate scores so one noisy batch doesn't dominate the forecast.
    raw_total_score = sum(x["score"] for x in scored)
    total_score = max(-75, min(75, raw_total_score))
    max_impact = max([x["impact"] for x in scored], default=0)

    if total_score >= 25:
        news_bias = "Bullish"
    elif total_score <= -25:
        news_bias = "Bearish"
    else:
        news_bias = "Neutral"

    if max_impact >= 8:
        severity = "HIGH"
    elif max_impact >= 4:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    return {
        "service": "execution_service",
        "module": "news_impact_engine_v3",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "available": bool(rows),
        "source": source,
        "news_bias": news_bias,
        "news_score": total_score,
        "raw_news_score": raw_total_score,
        "severity": severity,
        "headline_count": len(rows),
        "top_headlines": scored[:5],
        "note": "Live Massive Benzinga news scored" if rows else "No news returned",
    }

"""Market-sentiment sub-score (20%) — recent news headlines classified by Claude.

Pipeline: fetch recent headlines (Google News RSS, no key) for the company, then
ask the Claude API to rate overall sentiment 0-100 from those headlines, focused
on quarterly results and corporate announcements. Degrades gracefully: if the
Anthropic key/package is missing or there's no news, the sub-score is marked
unavailable (and simply drops out of the weighting).
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote
from xml.etree import ElementTree

from .. import net
from ..config import SECRET_ANTHROPIC_KEY, get_secret
from .models import SubScore, clamp

log = logging.getLogger("stockerr.scoring.sentiment")

SENTIMENT_MODEL = "claude-haiku-4-5-20251001"  # cheap classifier; configurable
NEWS_RSS = "https://news.google.com/rss/search?q={q}+when:30d&hl=en-IN&gl=IN&ceid=IN:en"


def fetch_headlines(query: str, limit: int = 12, timeout: int = 15) -> list[str]:
    url = NEWS_RSS.format(q=quote(query))
    try:
        resp = net.get(url, timeout=timeout)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("News fetch failed for %s: %s", query, exc)
        return []
    titles = [el.text.strip() for el in root.iter("title") if el.text and el.text.strip()]
    # First <title> is the feed name; drop it.
    return titles[1:limit + 1] if len(titles) > 1 else []


def _classify_with_claude(company: str, headlines: list[str], api_key: str) -> tuple[float, str] | None:
    try:
        import anthropic
    except Exception:
        log.warning("anthropic not installed; skipping sentiment. "
                    "Install with: pip install 'stockerr[scoring]'")
        return None

    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
    prompt = (
        f"Recent news headlines about {company} (an Indian listed company):\n\n"
        f"{numbered}\n\n"
        "Rate the OVERALL market sentiment these convey, focusing on quarterly "
        "results and corporate announcements. Reply with STRICT JSON only:\n"
        '{"sentiment_score": <integer 0-100, 0=very negative, 50=neutral, '
        '100=very positive>, "rationale": "<one short sentence>"}'
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=SENTIMENT_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("Claude sentiment call failed for %s: %s", company, exc)
        return None

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        log.warning("Could not parse sentiment JSON for %s: %r", company, text[:120])
        return None
    try:
        data = json.loads(m.group(0))
        score = clamp(float(data["sentiment_score"]))
        return score, str(data.get("rationale", ""))[:200]
    except Exception:
        return None


def score_sentiment(symbol: str, name: str | None = None) -> SubScore:
    api_key = get_secret(SECRET_ANTHROPIC_KEY)
    if not api_key:
        return SubScore.unavailable("sentiment", "no Anthropic API key (run `stockerr init`)")

    query = name or symbol
    headlines = fetch_headlines(query)
    if not headlines:
        return SubScore.unavailable("sentiment", "no recent news found")

    result = _classify_with_claude(query, headlines, api_key)
    if result is None:
        return SubScore.unavailable("sentiment", "sentiment classification unavailable")

    score, rationale = result
    return SubScore("sentiment", True, score,
                    {"headlines_used": len(headlines), "rationale": rationale}, "")

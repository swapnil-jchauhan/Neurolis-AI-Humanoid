"""
edge_search.py - High-speed, zero-cost, low-token search & live knowledge engine for Project Neurolis Mark II.
-------------------------------------------------------------------------------------------------------------
Combines:
  1. Live Weather Telemetry (instant ~150ms real-time temperature, condition, humidity, wind via wttr.in)
  2. Wikipedia Official REST API + OpenSearch fallback (instant ~120-250ms factual summaries for entities, science, history, concepts)
  3. DuckDuckGo Python Engine (ddgs) (real-time news, current events, sports scores, latest breakthroughs)
  4. Extractive Salience & Noise Scrubber (condenses live web context to < 80 tokens, keeping Groq prompt compact)
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Optional

# Try modern ddgs package first, fallback to legacy duckduckgo_search
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


def _clean_query_text(user_text: str) -> str:
    """Strips conversational fluff and punctuation to leave a sharp search query."""
    q = user_text.strip()
    patterns = [
        r"^(neurolis|robot|hey neurolis|can you|could you|please)\s+",
        r"^(search the web for|search the web|search for|search|look up|google|find out|do research on|deep research on|do deep research on|research on|research)\s+",
        r"^(tell me about|tell me|who is|what is|what are|where is|when was)\s+",
        r"\b(right now|today|at the moment)\b",
    ]
    for pat in patterns:
        q = re.sub(pat, "", q, flags=re.IGNORECASE).strip()
    # Strip leading/trailing punctuation (e.g. '?', '!', '.')
    q = q.strip("?!. \t\n\r")
    return q if q else user_text.strip().strip("?!. \t\n\r")


def get_live_weather(query: str, timeout: float = 2.5) -> Optional[str]:
    """
    Fetches real-time weather telemetry (temp, condition, humidity, wind) via wttr.in in ~150ms.
    100% Free, zero tokens, zero API keys.
    Defaults to Shimla (Auckland House School) if no city is explicitly specified.
    """
    clean_q = query.lower()
    m = re.search(r"\b(?:in|at|for|of)\s+([a-zA-Z\s]+)", clean_q)
    city = "Shimla"
    if m:
        candidate = m.group(1).strip()
        candidate = re.sub(r"\b(today|now|right now|currently|tonight|tomorrow|weather|temperature|forecast|mausam)\b", "", candidate).strip()
        candidate = candidate.strip("?!. \t\n\r")
        if candidate and len(candidate) > 2:
            city = candidate.title()
    elif any(c in clean_q for c in ["delhi", "mumbai", "london", "paris", "tokyo", "bangalore", "chandigarh", "new york"]):
        for c in ["delhi", "mumbai", "london", "paris", "tokyo", "bangalore", "chandigarh", "new york"]:
            if c in clean_q:
                city = c.title()
                break

    try:
        fmt = "%l: %C, %t, humidity %h, wind %w"
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format={urllib.parse.quote(fmt)}"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8").strip()
            # Clean emojis and non-ascii artifacts for robust cross-platform TTS
            text = re.sub(r"[^\x00-\x7F]+", "", text)
            text = " ".join(text.split())
            if text and len(text) > 5 and "unknown location" not in text.lower():
                return text
    except Exception:
        pass
    return None


def search_wikipedia_fast(query: str, timeout: float = 2.5) -> Optional[str]:
    """
    Fetches clean 1-2 sentence encyclopedic summary via Wikipedia REST API + OpenSearch in ~120-250ms.
    100% Free, zero tokens, zero API keys.
    """
    clean_q = _clean_query_text(query)
    if not clean_q:
        return None

    headers = {
        "User-Agent": "ProjectNeurolis/2.0 (HighSchoolRobotics; educational exhibition prototype)"
    }

    # 1. Direct title summary lookup
    try:
        encoded = urllib.parse.quote(clean_q.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            extract = data.get("extract", "")
            if extract and len(extract) > 20 and "may refer to:" not in extract.lower():
                sentences = re.split(r"(?<=[.!?])\s+", extract)
                condensed = " ".join(sentences[:2]).strip()
                words = condensed.split()[:45]
                return " ".join(words).strip()
    except Exception:
        pass

    # 2. OpenSearch resolution fallback (handles entities with prefixes/articles like 'capital of France')
    try:
        search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_q)}&limit=1&namespace=0&format=json"
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if len(data) > 1 and data[1]:
                target = data[1][0].replace(" ", "_")
                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(target)}"
                req2 = urllib.request.Request(summary_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    data2 = json.loads(resp2.read().decode("utf-8"))
                    extract2 = data2.get("extract", "")
                    if extract2 and len(extract2) > 20 and "may refer to:" not in extract2.lower():
                        sentences = re.split(r"(?<=[.!?])\s+", extract2)
                        condensed = " ".join(sentences[:2]).strip()
                        words = condensed.split()[:45]
                        return " ".join(words).strip()
    except Exception:
        pass

    return None


def search_ddg_fast(query: str, max_results: int = 2, timeout: float = 4.5) -> Optional[str]:
    """
    Fetches real-time search snippets via DuckDuckGo without API keys.
    Scrubs URLs, boilerplate, and ads, returning top salient factual sentences.
    """
    if DDGS is None:
        return None

    clean_q = _clean_query_text(query)
    if not clean_q:
        return None

    try:
        with DDGS(timeout=int(timeout)) as ddgs:
            results = list(ddgs.text(clean_q, max_results=max_results))
            if not results:
                return None

            snippets = []
            for r in results:
                body = r.get("body", "")
                if not body:
                    continue
                # Scrub URLs, bracketed refs, and redundant whitespace
                body = re.sub(r"https?://\S+", "", body)
                body = re.sub(r"\[.*?\]", "", body)
                body = " ".join(body.split())
                if len(body) > 20:
                    snippets.append(body)

            if not snippets:
                return None

            combined = " ".join(snippets)
            # Extractive sentence splitting
            sentences = re.split(r"(?<=[.!?])\s+", combined)
            selected = []
            count = 0
            boilerplate_filters = [
                "click here", "subscribe", "privacy policy", "cookie", "all rights reserved",
                "read more", "sign up", "terms of service", "advertisement"
            ]
            for s in sentences:
                s_clean = s.strip()
                words = s_clean.split()
                if len(words) >= 4 and not any(bp in s_clean.lower() for bp in boilerplate_filters):
                    selected.append(s_clean)
                    count += len(words)
                    if count >= 45:
                        break

            res_text = " ".join(selected) if selected else combined
            words = res_text.split()[:55]
            return " ".join(words).strip()
    except Exception:
        pass

    return None


def get_condensed_search_context(query: str, deep: bool = False) -> Optional[str]:
    """
    Intelligently routes query to Live Weather, Wikipedia, or DuckDuckGo and formats a < 80 token context block.
    Returns:
      '[LIVE WEATHER: ...]', '[FACT: ...]', '[LIVE WEB: ...]', or None if unreachable.
    """
    clean_q = _clean_query_text(query)
    low_q = clean_q.lower()

    # 1. Weather & Atmospheric Conditions (wttr.in instant live telemetry)
    is_weather = any(kw in low_q for kw in ["weather", "temperature", "forecast", "mausam", "rain", "raining", "wind speed", "humidity"])
    if is_weather:
        weather_info = get_live_weather(clean_q)
        if weather_info:
            return f"[LIVE WEATHER: {weather_info}]"

    # 2. Live Temporal Queries (news, sports scores, stocks, latest events)
    is_live_temporal = any(kw in low_q for kw in [
        "news", "today", "yesterday", "score", "match", "stock", "price",
        "current", "latest", "now", "recent", "who won", "president", "prime minister", "winner"
    ])

    if not is_live_temporal and not deep:
        # Factual entity / science concept -> try Wikipedia first (faster, ~120ms)
        wiki = search_wikipedia_fast(clean_q)
        if wiki:
            return f"[FACT: {wiki}]"

    # 3. DuckDuckGo for live/temporal, deep, or non-Wikipedia entities
    max_res = 3 if deep else 2
    ddg = search_ddg_fast(clean_q, max_results=max_res)
    if ddg:
        return f"[LIVE WEB: {ddg}]"

    # 4. Fallback to Wikipedia if DDG had no results
    wiki_fallback = search_wikipedia_fast(clean_q)
    if wiki_fallback:
        return f"[FACT: {wiki_fallback}]"

    return None

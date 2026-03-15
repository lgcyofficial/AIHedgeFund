import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


class LiveNewsService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("GEMINI_NEWS_MODEL", "gemini-2.0-flash")
        self.refresh_seconds = float(os.getenv("LIVE_NEWS_REFRESH_SECONDS", "18"))
        self.request_timeout = float(os.getenv("LIVE_NEWS_TIMEOUT_SECONDS", "3.0"))
        self.max_items = int(os.getenv("LIVE_NEWS_MAX_ITEMS", "8"))
        self._cache_until = 0.0
        self._cached_items: List[Dict[str, Any]] = []

    def fetch(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        now = time.time()
        if now < self._cache_until and self._cached_items:
            return list(self._cached_items)

        raw_items = self._fetch_google_news()
        if not raw_items:
            self._cached_items = []
            self._cache_until = now + min(self.refresh_seconds, 5)
            return []

        enriched = self._enrich_with_gemini(raw_items, prices) if self.api_key else None
        normalized = self._normalize_items(enriched or raw_items, prices, gemini_used=bool(enriched))
        self._cached_items = normalized[: self.max_items]
        self._cache_until = now + self.refresh_seconds
        return list(self._cached_items)

    def _fetch_google_news(self) -> List[Dict[str, Any]]:
        queries = [
            "artificial intelligence stocks OR Nvidia OR Apple OR Amazon OR Tesla",
            "bitcoin OR crypto markets",
            "federal reserve OR inflation markets",
        ]
        items: List[Dict[str, Any]] = []
        seen_titles = set()

        for query in queries:
            encoded = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            try:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                    payload = response.read()
            except Exception:
                continue

            try:
                root = ET.fromstring(payload)
            except ET.ParseError:
                continue

            for item in root.findall(".//item"):
                title = unescape((item.findtext("title") or "").strip())
                if not title or title in seen_titles:
                    continue

                source = item.findtext("source") or "Google News"
                published = self._format_time(item.findtext("pubDate"))
                items.append(
                    {
                        "title": title,
                        "time": published,
                        "source": source,
                    }
                )
                seen_titles.add(title)
                if len(items) >= self.max_items * 2:
                    return items

        return items

    def _enrich_with_gemini(self, raw_items: List[Dict[str, Any]], prices: Dict[str, float]) -> Optional[List[Dict[str, Any]]]:
        prompt = (
            "You are classifying financial headlines for a hedge fund dashboard.\n"
            "Return strict JSON only.\n"
            "Return an array of objects using only these keys: title, time, source, category, sentiment, impact_score, assets.\n"
            "Rules:\n"
            "- Reuse the exact title, time, and source from the input.\n"
            "- category must be one of: equities, macro, crypto, policy, market.\n"
            "- sentiment must be one of: positive, negative, neutral.\n"
            "- impact_score must be between 0.10 and 0.95.\n"
            "- assets must be selected only from: NVDA, AAPL, AMZN, TSLA, BTC.\n"
            "- Keep the same number of items as the input.\n"
            f"Current prices: {json.dumps(prices)}\n"
            f"Input headlines: {json.dumps(raw_items)}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.15,
                "responseMimeType": "application/json",
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else None
        except Exception:
            return None

    def _normalize_items(
        self,
        items: List[Dict[str, Any]],
        prices: Dict[str, float],
        gemini_used: bool,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in items:
            title = str(item.get("title", "")).strip()
            if not title:
                continue

            assets = self._extract_assets(title, prices, item.get("assets"))
            sentiment = self._normalize_sentiment(item.get("sentiment"), title)
            category = self._normalize_category(item.get("category"), title, assets)
            impact_score = self._normalize_impact(item.get("impact_score"), title, assets, sentiment)
            source = str(item.get("source", "Google News")).strip() or "Google News"
            if gemini_used:
                source = f"{source} / Gemini"

            normalized.append(
                {
                    "title": title,
                    "time": str(item.get("time", "")).strip() or datetime.now().strftime("%H:%M:%S"),
                    "category": category,
                    "sentiment": sentiment,
                    "impact_score": impact_score,
                    "assets": assets,
                    "source": source,
                }
            )
        return normalized

    def _extract_assets(self, title: str, prices: Dict[str, float], supplied: Any) -> List[str]:
        if isinstance(supplied, list):
            assets = [str(asset).upper() for asset in supplied if str(asset).upper() in prices]
            if assets:
                return assets[:3]

        lowered = title.lower()
        mapped = [asset for asset in prices if asset.lower() in lowered]
        aliases = {
            "nvidia": "NVDA",
            "apple": "AAPL",
            "amazon": "AMZN",
            "tesla": "TSLA",
            "bitcoin": "BTC",
            "crypto": "BTC",
        }
        for alias, asset in aliases.items():
            if alias in lowered and asset not in mapped:
                mapped.append(asset)
        return mapped[:3] or ["MARKET"]

    def _normalize_sentiment(self, supplied: Any, title: str) -> str:
        candidate = str(supplied or "").lower()
        if candidate in {"positive", "negative", "neutral"}:
            return candidate

        lowered = title.lower()
        positive = ("beat", "surge", "gain", "up", "growth", "rally", "soar", "strong")
        negative = ("fall", "down", "drop", "tariff", "risk", "selloff", "pressure", "hotter")
        if any(token in lowered for token in positive):
            return "positive"
        if any(token in lowered for token in negative):
            return "negative"
        return "neutral"

    def _normalize_category(self, supplied: Any, title: str, assets: List[str]) -> str:
        candidate = str(supplied or "").lower()
        if candidate in {"equities", "macro", "crypto", "policy", "market"}:
            return candidate

        lowered = title.lower()
        if "fed" in lowered or "inflation" in lowered or "rates" in lowered:
            return "policy"
        if "bitcoin" in lowered or "crypto" in lowered or "btc" in lowered or assets == ["BTC"]:
            return "crypto"
        if any(asset in {"NVDA", "AAPL", "AMZN", "TSLA"} for asset in assets):
            return "equities"
        return "market"

    def _normalize_impact(self, supplied: Any, title: str, assets: List[str], sentiment: str) -> float:
        try:
            value = float(supplied)
            return round(max(0.1, min(value, 0.95)), 2)
        except Exception:
            pass

        impact = 0.34 + min(len(assets), 3) * 0.11
        lowered = title.lower()
        if any(token in lowered for token in ("fed", "inflation", "rates", "tariff", "earnings")):
            impact += 0.12
        if sentiment != "neutral":
            impact += 0.1
        return round(max(0.1, min(impact, 0.95)), 2)

    def _format_time(self, value: Optional[str]) -> str:
        if not value:
            return datetime.now().strftime("%H:%M:%S")
        try:
            parsed = parsedate_to_datetime(value)
            return parsed.astimezone().strftime("%H:%M:%S")
        except Exception:
            return datetime.now().strftime("%H:%M:%S")

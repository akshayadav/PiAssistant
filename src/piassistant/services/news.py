from __future__ import annotations

import httpx

from ..config import Settings
from .base import BaseService
from .cache import CacheService


class NewsService(BaseService):
    """NewsAPI.org news data with cache-first fetching."""

    name = "news"
    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, settings: Settings, cache: CacheService):
        self.api_key = settings.newsapi_key
        self.cache = cache
        self.ttl = settings.news_cache_ttl
        self._client = httpx.AsyncClient(timeout=10)

    async def get_headlines(self, category: str = "general", country: str = "us", count: int = 5) -> list[dict]:
        """Get top headlines. Cache-first."""
        cache_key = f"news:headlines:{country}:{category}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached[:count]

        resp = await self._client.get(
            f"{self.BASE_URL}/top-headlines",
            params={
                "country": country,
                "category": category,
                "pageSize": max(count, 10),  # fetch a few extra for cache
                "apiKey": self.api_key,
            },
        )
        resp.raise_for_status()
        raw = resp.json()

        articles = []
        for a in raw.get("articles", []):
            articles.append({
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "source": a.get("source", {}).get("name", ""),
                "url": a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
            })
        await self.cache.set(cache_key, articles, self.ttl)
        return articles[:count]

    async def search(self, query: str, count: int = 5) -> list[dict]:
        """Search news articles by keyword."""
        cache_key = f"news:search:{query.lower()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached[:count]

        resp = await self._client.get(
            f"{self.BASE_URL}/everything",
            params={
                "q": query,
                "sortBy": "publishedAt",
                "pageSize": max(count, 10),
                "apiKey": self.api_key,
            },
        )
        resp.raise_for_status()
        raw = resp.json()

        articles = []
        for a in raw.get("articles", []):
            articles.append({
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "source": a.get("source", {}).get("name", ""),
                "url": a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
            })
        await self.cache.set(cache_key, articles, self.ttl)
        return articles[:count]

    async def health_check(self) -> dict:
        if not self.api_key:
            return {"healthy": False, "details": "No NewsAPI key"}
        return {"healthy": True, "details": "NewsAPI configured"}

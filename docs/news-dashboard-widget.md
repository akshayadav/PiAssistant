# News Dashboard Widget

## The Idea

PiAssistant's kiosk dashboard needed a news widget to show headlines at a glance — no need to ask Claude via chat. The goal: a configurable set of news feeds (global, India, local cities) displayed as compact headline lists, refreshing on a cadence that respects the NewsAPI free tier.

## What It Shows

By default, 4 news feeds:

| Feed | Type | Source | Count |
|---|---|---|---|
| Global | Top headlines | US general news | 10 |
| India | Top headlines | Indian news | 10 |
| Indore | Search | Articles mentioning "Indore India" | 3 |
| Santa Clara | Search | Articles mentioning "Santa Clara California" | 3 |

Each feed appears as a card with the feed name and a compact list of headlines (title + source). Feeds can be added/removed from the dashboard UI, just like weather cities.

## API Budget

NewsAPI free tier: **100 requests/day**.

| Feed | API Call | Requests/refresh |
|---|---|---|
| Global headlines | `/top-headlines?country=us&category=general` | 1 |
| India headlines | `/top-headlines?country=in` | 1 |
| Indore news | `/everything?q=Indore India` | 1 |
| Santa Clara news | `/everything?q=Santa Clara California` | 1 |
| **Total per refresh** | | **4** |

With a **6-hour dashboard cache TTL**: 4 feeds × 4 refreshes/day = **16 requests/day**, leaving 84 for chat tool use.

## Architecture

```
Dashboard (browser)
    │
    │  polls GET /api/news/feeds every 30 min
    │
    ▼
FastAPI (routes_kiosk.py)
    │
    │  checks in-memory cache (6h TTL per feed)
    │  on cache miss → fetches from NewsAPI
    │
    ├── headlines feeds → NewsService.get_headlines()
    └── search feeds   → NewsService.search()
    │
    │  results cached with news_dashboard_ttl (21600s)
    │
    ▼
SQLite (news_feeds table)
    stores feed configuration (name, type, country, query, count)
    seeded with 4 defaults on first access
```

Key design decisions:

| Decision | Choice | Why |
|---|---|---|
| Cache TTL | 6 hours (separate from 30-min chat cache) | Conserve API budget — news headlines don't change that fast |
| Dashboard poll | 30 minutes | Serves from cache; actual API calls only on 6-hour miss |
| Storage | SQLite `news_feeds` table | Persistent, user can add/remove feeds and they survive restarts |
| Feed types | "headlines" + "search" | Maps to NewsAPI's two main endpoints |
| Default seeding | On first GET if table is empty | Same pattern as weather cities |

## Implementation Details

### Files Changed

| File | Change |
|---|---|
| `src/piassistant/config.py` | Added `news_dashboard_ttl: int = 21600` |
| `src/piassistant/services/storage.py` | Added `news_feeds` table to schema |
| `src/piassistant/api/routes_kiosk.py` | Added GET/POST/DELETE `/api/news/feeds` endpoints |
| `src/piassistant/static/index.html` | Added news widget HTML + add-feed form |
| `src/piassistant/static/css/dashboard.css` | Added news widget styles |
| `src/piassistant/static/js/dashboard.js` | Added news fetch, render, add/remove functions |

No new service file — reuses existing `NewsService` methods (`get_headlines` and `search`).

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS news_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,          -- "headlines" or "search"
    country TEXT DEFAULT '',     -- for headlines: "us", "in"
    category TEXT DEFAULT 'general',
    query TEXT DEFAULT '',       -- for search: "Indore India", etc.
    count INTEGER DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### API Endpoints

**GET /api/news/feeds** — Returns all feeds with cached articles:
```json
[
  {
    "id": 1,
    "name": "Global",
    "articles": [
      {"title": "...", "source": "CNN", "published_at": "..."}
    ]
  }
]
```

**POST /api/news/feeds** — Add a new feed:
```json
{"name": "Technology", "type": "headlines", "country": "us", "category": "technology", "count": 5}
```

**DELETE /api/news/feeds/{id}** — Remove a feed (also clears its cache).

### Two-Tier Caching

The news widget uses a **separate, longer cache** from the chat tools:

| Context | Cache key pattern | TTL | Why |
|---|---|---|---|
| Chat tools | `news:headlines:us:general` | 30 min (`news_cache_ttl`) | User expects fresh results when asking |
| Dashboard widget | `news_dashboard:{feed_id}` | 6 hours (`news_dashboard_ttl`) | Passive display, budget conservation |

This means chat and dashboard don't share cache entries — each has its own TTL appropriate to the use case.

### Dashboard Widget

The news widget spans full width (like grocery/weather). Each feed renders as a card with:
- Feed name in accent color
- Hover-reveal × button to remove
- Compact headline list (title + source)

The + button opens a form to add feeds — choose between "Headlines" (pick a country) or "Search" (enter a query).

## Testing

```bash
# Verify feeds endpoint returns 4 default feeds with articles
curl http://piassistant-mothership.local:8000/api/news/feeds

# Add a new feed
curl -X POST http://piassistant-mothership.local:8000/api/news/feeds \
  -H "Content-Type: application/json" \
  -d '{"name": "Technology", "type": "headlines", "country": "us", "category": "technology", "count": 5}'

# Remove a feed
curl -X DELETE http://piassistant-mothership.local:8000/api/news/feeds/5
```

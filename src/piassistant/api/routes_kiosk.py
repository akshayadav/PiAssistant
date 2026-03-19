import asyncio
import logging

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared httpx client for Newsdata.io calls
_newsdata_client = httpx.AsyncClient(timeout=10)


# --- Weather Cities ---

DEFAULT_WEATHER_CITIES = [
    ("Santa Clara, CA", "Santa Clara, CA"),
    ("Palo Alto, CA", "Palo Alto, CA"),
    ("Idaho Falls, ID", "Idaho Falls, ID"),
    ("Indore, MP, India", "Indore, India"),
    ("Ahmedabad, Gujarat, India", "Ahmedabad, India"),
]


class WeatherCityRequest(BaseModel):
    name: str
    display_name: str = ""


@router.get("/weather/cities")
async def get_weather_cities(request: Request):
    """Get all tracked weather cities with current conditions."""
    storage = request.app.state.registry.get("storage")
    weather = request.app.state.registry.get("weather")

    db = await storage.connect()
    try:
        cursor = await db.execute("SELECT id, name, display_name FROM weather_cities ORDER BY id")
        rows = await cursor.fetchall()
    finally:
        await db.close()

    if not rows:
        # Seed defaults on first access
        db = await storage.connect()
        try:
            for name, display in DEFAULT_WEATHER_CITIES:
                await db.execute(
                    "INSERT OR IGNORE INTO weather_cities (name, display_name) VALUES (?, ?)",
                    (name, display),
                )
            await db.commit()
            cursor = await db.execute("SELECT id, name, display_name FROM weather_cities ORDER BY id")
            rows = await cursor.fetchall()
        finally:
            await db.close()

    # Fetch weather for all cities in parallel
    async def fetch_one(city_id, name, display_name):
        try:
            data = await weather.get_current(location=name)
            return {
                "id": city_id,
                "name": name,
                "display_name": display_name,
                "temp": data["temp_f"],
                "feel": data["feels_like_f"],
                "desc": data["description"],
                "hum": data["humidity"],
                "wind": data["wind_mph"],
                "timezone": data.get("timezone", "UTC"),
            }
        except Exception:
            return {
                "id": city_id,
                "name": name,
                "display_name": display_name,
                "temp": None,
                "desc": "Unavailable",
            }

    tasks = [fetch_one(r[0], r[1], r[2]) for r in rows]
    results = await asyncio.gather(*tasks)
    return list(results)


@router.post("/weather/cities")
async def add_weather_city(request: Request, body: WeatherCityRequest):
    storage = request.app.state.registry.get("storage")
    display = body.display_name or body.name
    db = await storage.connect()
    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO weather_cities (name, display_name) VALUES (?, ?)",
            (body.name, display),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "name": body.name, "display_name": display}
    finally:
        await db.close()


@router.delete("/weather/cities/{city_id}")
async def delete_weather_city(request: Request, city_id: int):
    storage = request.app.state.registry.get("storage")
    db = await storage.connect()
    try:
        cursor = await db.execute("DELETE FROM weather_cities WHERE id = ?", (city_id,))
        await db.commit()
        return {"deleted": cursor.rowcount > 0}
    finally:
        await db.close()


# --- News Feeds ---

DEFAULT_NEWS_FEEDS = [
    # (name, type, country, category, query, count, provider)
    ("Global", "headlines", "us", "general", "", 10, "newsapi"),
    ("India", "headlines", "in", "general", "", 10, "newsdata"),
    ("Indore", "search", "", "general", "Indore India", 3, "newsapi"),
    ("Santa Clara", "search", "", "general", "Santa Clara California", 3, "newsapi"),
]


class NewsFeedRequest(BaseModel):
    name: str
    type: str = "headlines"  # "headlines" or "search"
    country: str = ""
    category: str = "general"
    query: str = ""
    count: int = 5
    provider: str = "newsapi"  # "newsapi" or "newsdata"


# Titles matching these patterns are filler, not real headlines
_NEWSDATA_JUNK = {"word of the day", "quote of the day", "reflections", "thought for the day",
                  "today's horoscope", "daily horoscope", "morning briefing"}


async def fetch_newsdata(api_key: str, country: str = "", query: str = "",
                         count: int = 10) -> list[dict]:
    """Fetch articles from Newsdata.io API, filtering filler content."""
    params = {"apikey": api_key, "language": "en", "prioritydomain": "top"}
    if country:
        params["country"] = country
    if query:
        params["q"] = query
    resp = await _newsdata_client.get(
        "https://newsdata.io/api/1/latest", params=params
    )
    resp.raise_for_status()
    raw = resp.json()
    articles = []
    for a in raw.get("results", []):
        title = a.get("title", "")
        # Skip filler content
        if any(junk in title.lower() for junk in _NEWSDATA_JUNK):
            continue
        articles.append({
            "title": title,
            "description": a.get("description", ""),
            "source": a.get("source_name", ""),
            "url": a.get("link", ""),
            "published_at": a.get("pubDate", ""),
        })
        if len(articles) >= count:
            break
    return articles


@router.get("/news/feeds")
async def get_news_feeds(request: Request):
    """Get all configured news feeds with cached articles."""
    storage = request.app.state.registry.get("storage")
    news = request.app.state.registry.get("news")
    cache = request.app.state.registry.get("cache")
    settings = request.app.state.settings

    db = await storage.connect()
    try:
        cursor = await db.execute(
            "SELECT id, name, type, country, category, query, count, provider "
            "FROM news_feeds ORDER BY id"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    if not rows:
        # Seed defaults on first access
        db = await storage.connect()
        try:
            for name, ftype, country, category, query, count, provider in DEFAULT_NEWS_FEEDS:
                await db.execute(
                    "INSERT INTO news_feeds (name, type, country, category, query, count, provider) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, ftype, country, category, query, count, provider),
                )
            await db.commit()
            cursor = await db.execute(
                "SELECT id, name, type, country, category, query, count, provider "
                "FROM news_feeds ORDER BY id"
            )
            rows = await cursor.fetchall()
        finally:
            await db.close()

    dashboard_ttl = settings.news_dashboard_ttl
    newsdata_key = settings.newsdata_api_key

    async def fetch_feed(feed_id, name, ftype, country, category, query, count, provider):
        cache_key = f"news_dashboard:{feed_id}"
        cached = await cache.get(cache_key)
        if cached is not None:
            return {"id": feed_id, "name": name, "articles": cached}
        try:
            if provider == "newsdata" and newsdata_key:
                articles = await fetch_newsdata(
                    api_key=newsdata_key, country=country, query=query, count=count
                )
            elif ftype == "headlines":
                articles = await news.get_headlines(
                    category=category, country=country, count=count
                )
            else:
                articles = await news.search(query=query, count=count)
            await cache.set(cache_key, articles, dashboard_ttl)
            return {"id": feed_id, "name": name, "articles": articles}
        except Exception as e:
            logger.warning("News feed %s failed: %s", name, e)
            return {"id": feed_id, "name": name, "articles": []}

    tasks = [
        fetch_feed(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


@router.post("/news/feeds")
async def add_news_feed(request: Request, body: NewsFeedRequest):
    storage = request.app.state.registry.get("storage")
    db = await storage.connect()
    try:
        cursor = await db.execute(
            "INSERT INTO news_feeds (name, type, country, category, query, count, provider) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (body.name, body.type, body.country, body.category, body.query, body.count, body.provider),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "name": body.name}
    finally:
        await db.close()


@router.delete("/news/feeds/{feed_id}")
async def delete_news_feed(request: Request, feed_id: int):
    storage = request.app.state.registry.get("storage")
    cache = request.app.state.registry.get("cache")
    db = await storage.connect()
    try:
        cursor = await db.execute("DELETE FROM news_feeds WHERE id = ?", (feed_id,))
        await db.commit()
        # Clear cached articles for this feed
        await cache.invalidate(f"news_dashboard:{feed_id}")
        return {"deleted": cursor.rowcount > 0}
    finally:
        await db.close()


# --- Orders ---

@router.get("/orders")
async def get_orders(request: Request):
    """Get undelivered Amazon orders."""
    orders = request.app.state.registry.get("orders")
    return await orders.get_undelivered()


@router.post("/orders/refresh")
async def refresh_orders(request: Request):
    """Force refresh Amazon order data."""
    orders = request.app.state.registry.get("orders")
    return await orders.force_refresh()


# --- Grocery ---

class GroceryAddRequest(BaseModel):
    store: str
    item: str
    quantity: str = ""


@router.get("/grocery")
async def get_grocery(request: Request, store: str = None):
    grocery = request.app.state.registry.get("grocery")
    return await grocery.get_list(store=store)


@router.post("/grocery/add")
async def add_grocery(request: Request, body: GroceryAddRequest):
    grocery = request.app.state.registry.get("grocery")
    return await grocery.add_item(store=body.store, item=body.item, quantity=body.quantity)


@router.post("/grocery/{item_id}/done")
async def check_grocery(request: Request, item_id: int):
    grocery = request.app.state.registry.get("grocery")
    return {"checked": await grocery.check_item(item_id, done=True)}


@router.delete("/grocery/{item_id}")
async def delete_grocery(request: Request, item_id: int):
    grocery = request.app.state.registry.get("grocery")
    return {"removed": await grocery.remove_item(item_id)}


# --- Timers ---

@router.get("/timers")
async def get_timers(request: Request):
    timers = request.app.state.registry.get("timers")
    result = await timers.list_timers()
    fired = timers.get_fired_events()
    return {"timers": result, "fired": fired}


# --- Reminders ---

@router.get("/reminders")
async def get_reminders(request: Request):
    reminders = request.app.state.registry.get("reminders")
    return await reminders.list_reminders()


@router.post("/reminders/{reminder_id}/done")
async def complete_reminder(request: Request, reminder_id: int):
    reminders = request.app.state.registry.get("reminders")
    return {"completed": await reminders.complete_reminder(reminder_id)}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(request: Request, reminder_id: int):
    reminders = request.app.state.registry.get("reminders")
    return {"deleted": await reminders.delete_reminder(reminder_id)}


# --- Notes ---

@router.get("/notes")
async def get_notes(request: Request):
    reminders = request.app.state.registry.get("reminders")
    return await reminders.list_notes()


@router.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: int):
    reminders = request.app.state.registry.get("reminders")
    return {"deleted": await reminders.delete_note(note_id)}


# --- Todos ---

@router.get("/todos")
async def get_todos(request: Request):
    todo = request.app.state.registry.get("todo")
    return await todo.get_list()


@router.post("/todos/{item_id}/done")
async def complete_todo(request: Request, item_id: int):
    todo = request.app.state.registry.get("todo")
    return {"completed": await todo.complete_item(item_id)}


@router.delete("/todos/{item_id}")
async def delete_todo(request: Request, item_id: int):
    todo = request.app.state.registry.get("todo")
    return {"deleted": await todo.delete_item(item_id)}

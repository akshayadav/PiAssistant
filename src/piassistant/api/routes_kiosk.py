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
            temp_f = data["temp_f"]
            feel_f = data["feels_like_f"]
            wind_mph = data["wind_mph"]
            return {
                "id": city_id,
                "name": name,
                "display_name": display_name,
                "temp_f": temp_f,
                "temp_c": round((temp_f - 32) * 5 / 9, 1) if temp_f is not None else None,
                "feel_f": feel_f,
                "feel_c": round((feel_f - 32) * 5 / 9, 1) if feel_f is not None else None,
                "desc": data["description"],
                "hum": data["humidity"],
                "wind_mph": wind_mph,
                "wind_kph": round(wind_mph * 1.609, 1) if wind_mph is not None else None,
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


# --- Calendar ---

@router.get("/calendar/events")
async def get_calendar_events(request: Request, days: int = 7):
    """Get upcoming calendar events from Google and/or iCloud."""
    calendar = request.app.state.registry.get("calendar")
    return await calendar.get_events(days=days)


# --- Network Devices ---

class NetworkDeviceRequest(BaseModel):
    name: str
    hostname: str
    ip: str = ""
    device_type: str = "other"


@router.get("/network/devices")
async def list_network_devices(request: Request):
    """List all tracked network devices with online status."""
    network = request.app.state.registry.get("network")
    return await network.list_devices()


@router.post("/network/devices")
async def add_network_device(request: Request, body: NetworkDeviceRequest):
    network = request.app.state.registry.get("network")
    return await network.add_device(
        name=body.name, hostname=body.hostname, ip=body.ip, device_type=body.device_type
    )


@router.delete("/network/devices/{device_id}")
async def remove_network_device(request: Request, device_id: int):
    network = request.app.state.registry.get("network")
    return {"deleted": await network.remove_device(device_id)}


@router.post("/network/ping")
async def ping_all_devices(request: Request):
    """Manually trigger ping of all devices."""
    network = request.app.state.registry.get("network")
    return await network.ping_all()


# --- System Monitor ---

@router.get("/system")
async def get_system_status(request: Request):
    """Get current system metrics (CPU, RAM, disk, temp)."""
    sysmon = request.app.state.registry.get("sysmon")
    return await sysmon.get_status()


# --- Quote ---

@router.get("/quote")
async def get_daily_quote(request: Request):
    """Get the daily inspirational quote."""
    quote = request.app.state.registry.get("quote")
    return await quote.get_daily_quote()


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


# --- Tasks (unified todos + reminders) ---

@router.get("/tasks")
async def get_tasks(request: Request):
    """Get all active tasks and nudges."""
    tasks = request.app.state.registry.get("todo")
    return {
        "tasks": await tasks.get_tasks(),
        "nudges": tasks.get_nudges(),
    }


@router.post("/tasks/{task_id}/done")
async def complete_task(request: Request, task_id: int):
    tasks = request.app.state.registry.get("todo")
    return {"completed": await tasks.complete_task(task_id)}


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: int):
    tasks = request.app.state.registry.get("todo")
    return {"deleted": await tasks.delete_task(task_id)}


class TaskUpdateRequest(BaseModel):
    text: str = None
    priority: str = None
    due_at: str = None


@router.put("/tasks/{task_id}")
async def update_task(request: Request, task_id: int, body: TaskUpdateRequest):
    tasks = request.app.state.registry.get("todo")
    updated = await tasks.update_task(
        task_id=task_id, text=body.text, priority=body.priority, due_at=body.due_at
    )
    if not updated:
        return {"error": "Task not found"}
    return updated


# --- Notes ---

@router.get("/notes")
async def get_notes(request: Request):
    reminders = request.app.state.registry.get("reminders")
    return await reminders.list_notes()


@router.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: int):
    reminders = request.app.state.registry.get("reminders")
    return {"deleted": await reminders.delete_note(note_id)}

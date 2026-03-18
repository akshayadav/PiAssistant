import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


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

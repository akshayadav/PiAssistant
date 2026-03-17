from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


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

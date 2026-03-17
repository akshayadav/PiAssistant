TOOL_DEFINITIONS = [
    # --- Weather ---
    {
        "name": "get_current_weather",
        "description": "Get current weather for a location. Use when the user asks about weather, temperature, or conditions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, e.g. 'New York, NY' or 'London, UK'",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "get_weather_forecast",
        "description": "Get weather forecast for the next few days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, e.g. 'New York, NY'",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to forecast (1-5)",
                    "default": 3,
                },
            },
            "required": ["location"],
        },
    },
    # --- News ---
    {
        "name": "get_news_headlines",
        "description": "Get top news headlines. Use when user asks about news, what's happening, current events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["general", "business", "technology", "science", "sports", "health", "entertainment"],
                    "description": "News category",
                    "default": "general",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of headlines (1-10)",
                    "default": 5,
                },
            },
        },
    },
    {
        "name": "search_news",
        "description": "Search for news articles on a specific topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'AI robotics' or 'Raspberry Pi'",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results (1-10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    # --- Grocery ---
    {
        "name": "grocery_add",
        "description": "Add an item to a grocery store list. Default stores: Whole Foods, Sprouts, Indian Grocery, Costco, Target, Other. New store names are created automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store": {
                    "type": "string",
                    "description": "Store name, e.g. 'Whole Foods', 'Costco'",
                },
                "item": {
                    "type": "string",
                    "description": "Item to add, e.g. 'milk', 'bananas'",
                },
                "quantity": {
                    "type": "string",
                    "description": "Optional quantity, e.g. '2 lbs', '1 gallon'",
                    "default": "",
                },
            },
            "required": ["store", "item"],
        },
    },
    {
        "name": "grocery_list",
        "description": "Show the grocery list. Can filter by store or show all stores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store": {
                    "type": "string",
                    "description": "Optional store name to filter by. Omit for all stores.",
                },
            },
        },
    },
    {
        "name": "grocery_remove",
        "description": "Remove a grocery item by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": "The item ID to remove",
                },
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "grocery_clear",
        "description": "Clear all checked-off (done) grocery items. Optionally filter by store.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store": {
                    "type": "string",
                    "description": "Optional store name. Omit to clear all done items.",
                },
            },
        },
    },
    # --- Timers ---
    {
        "name": "timer_set",
        "description": "Set a cooking/general timer. Use when user says 'set a timer for X minutes'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Timer name, e.g. 'pizza', 'pasta', 'eggs'",
                },
                "seconds": {
                    "type": "integer",
                    "description": "Duration in seconds. Convert from minutes if needed (e.g. 12 minutes = 720).",
                },
            },
            "required": ["name", "seconds"],
        },
    },
    {
        "name": "timer_list",
        "description": "List all active timers and their remaining time.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "timer_cancel",
        "description": "Cancel a running timer by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Timer name to cancel",
                },
            },
            "required": ["name"],
        },
    },
    # --- Reminders ---
    {
        "name": "reminder_add",
        "description": "Add a reminder. Use when user says 'remind me to...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "What to be reminded about",
                },
                "due_at": {
                    "type": "string",
                    "description": "When the reminder is due, ISO format (e.g. '2026-03-18T10:00'). Leave empty if no specific time.",
                    "default": "",
                },
                "for_person": {
                    "type": "string",
                    "description": "Who the reminder is for (e.g. 'Akshay'). Leave empty if for the user.",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "reminder_list",
        "description": "List active reminders.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # --- Notes ---
    {
        "name": "note_add",
        "description": "Save a quick note. Use when user says 'note that...', 'remember that...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The note content",
                },
                "for_person": {
                    "type": "string",
                    "description": "Who the note is for",
                    "default": "",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Pin to top of notes list",
                    "default": False,
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "note_list",
        "description": "List all saved notes.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # --- To-Do ---
    {
        "name": "todo_add",
        "description": "Add a to-do item. Use when user says 'add to my to-do list'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The to-do item",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority: 'high', 'medium', 'low'",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "todo_list",
        "description": "List to-do items.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "todo_complete",
        "description": "Mark a to-do item as done by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": "The to-do item ID to complete",
                },
            },
            "required": ["item_id"],
        },
    },
]

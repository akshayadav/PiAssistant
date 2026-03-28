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
    # --- Orders ---
    {
        "name": "get_orders",
        "description": "Get undelivered Amazon orders with delivery status and tracking info.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "refresh_orders",
        "description": "Force refresh Amazon order data from Amazon.com. Use sparingly — only when explicitly asked.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # --- Grocery ---
    {
        "name": "grocery_add",
        "description": (
            "Add an item to a grocery store list. "
            "Stores: New India Bazaar, India Cash and Carry, Apna Mandi (Indian), "
            "Costco (Bulk), Safeway, Lucky, Target (Regular), Sprouts, Whole Foods (Produce), Amazon (Online). "
            "New store names are created automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "store": {
                    "type": "string",
                    "description": "Store name, e.g. 'Costco', 'New India Bazaar'",
                },
                "item": {
                    "type": "string",
                    "description": "Item to add, e.g. 'Basmati Rice', 'bananas'",
                },
                "quantity": {
                    "type": "string",
                    "description": "Optional quantity, e.g. '10 lb bag', '1 gallon'",
                    "default": "",
                },
                "price": {
                    "type": "number",
                    "description": "Optional price in dollars, e.g. 12.99",
                },
                "brand": {
                    "type": "string",
                    "description": "Optional brand, e.g. 'Daawat', 'Kirkland'",
                    "default": "",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes, e.g. 'organic', 'check sale price'",
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
    {
        "name": "grocery_find",
        "description": (
            "Search for a product and get smart store recommendations. "
            "Returns matching products from the catalog, recommended store category, "
            "recent prices, and saved preferences. Use this FIRST when the user wants to buy something."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name or keyword, e.g. 'rice', 'basmati rice', 'toilet paper'",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "grocery_stores",
        "description": "List all known stores grouped by category (Indian, Bulk, Regular, Produce, Online).",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category slug to filter: 'indian', 'bulk', 'regular', 'produce', 'online'",
                },
            },
        },
    },
    {
        "name": "grocery_price",
        "description": (
            "Record a price for a product at a store. Use when the user reports a price "
            "(e.g. 'rice was $13 at New India Bazaar'). Builds up price history over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name, e.g. 'Basmati Rice'",
                },
                "store_name": {
                    "type": "string",
                    "description": "Store name, e.g. 'New India Bazaar'",
                },
                "price": {
                    "type": "number",
                    "description": "Price in dollars, e.g. 12.99",
                },
                "quantity": {
                    "type": "string",
                    "description": "What quantity this price is for, e.g. '10 lb bag', '24 pack'",
                    "default": "",
                },
                "unit_price": {
                    "type": "number",
                    "description": "Optional price per unit for comparison, e.g. 1.30 per lb",
                },
            },
            "required": ["product_name", "store_name", "price"],
        },
    },
    {
        "name": "grocery_preference",
        "description": (
            "Save a user preference for a product. Use when the user says things like "
            "'I always get Daawat basmati from India Cash and Carry' or 'I prefer organic chicken'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name, e.g. 'Basmati Rice'",
                },
                "preferred_store": {
                    "type": "string",
                    "description": "Preferred store name, e.g. 'India Cash and Carry'",
                },
                "preferred_brand": {
                    "type": "string",
                    "description": "Preferred brand, e.g. 'Daawat', 'Kirkland'",
                    "default": "",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional preference notes, e.g. 'organic only', 'get the 20lb bag'",
                    "default": "",
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "grocery_prices",
        "description": (
            "Look up price history for a product across all stores. "
            "Use when user asks 'where is rice cheapest?' or 'what's the price of X?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name to look up prices for",
                },
            },
            "required": ["product_name"],
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
    # --- Tasks (unified todos + reminders) ---
    {
        "name": "task_add",
        "description": "Add a task or reminder. Use for 'add to my to-do list', 'remind me to...', action items, things to do.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The task or reminder text",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Task priority. Suggest one if user doesn't specify.",
                },
                "due_at": {
                    "type": "string",
                    "description": "Due date/time in ISO format (e.g. '2026-03-28T10:00'). Convert relative dates (e.g. 'tomorrow 10am'). Suggest one if user doesn't specify.",
                    "default": "",
                },
                "is_reminder": {
                    "type": "boolean",
                    "description": "Set true for lightweight reminders ('remind me to...'). False for action items/tasks.",
                    "default": False,
                },
                "for_person": {
                    "type": "string",
                    "description": "Who this is for (e.g. 'Akshay'). Leave empty if for the user.",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "task_list",
        "description": "List all active tasks and reminders, sorted by urgency (overdue first, then by priority).",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_done": {
                    "type": "boolean",
                    "description": "Include completed tasks",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "task_complete",
        "description": "Mark a task or reminder as done by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The task ID to complete",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_delete",
        "description": "Remove a task entirely (not just mark done — permanently delete).",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The task ID to delete",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_update",
        "description": "Update an existing task's priority, due date, or text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The task ID to update",
                },
                "text": {
                    "type": "string",
                    "description": "New task text",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low", ""],
                    "description": "New priority (empty string to clear)",
                },
                "due_at": {
                    "type": "string",
                    "description": "New due date in ISO format (empty string to clear)",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_suggest",
        "description": "Get all open tasks for AI scheduling analysis. Use when user asks 'what should I prioritize?', 'schedule my tasks', or 'what's most urgent?'. Analyze the list and suggest priorities/due dates, then use task_update to apply.",
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
    # --- Calendar ---
    {
        "name": "get_calendar_events",
        "description": "Get upcoming calendar events from Google Calendar and/or iCloud.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead (default 7)",
                    "default": 7,
                },
            },
        },
    },
    {
        "name": "add_calendar_event",
        "description": "Add an event to Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Event title",
                },
                "start": {
                    "type": "string",
                    "description": "Start time in ISO format, e.g. '2026-03-20T10:00:00'",
                },
                "end": {
                    "type": "string",
                    "description": "End time in ISO format, e.g. '2026-03-20T11:00:00'",
                },
                "description": {
                    "type": "string",
                    "description": "Optional event description",
                    "default": "",
                },
            },
            "required": ["summary", "start", "end"],
        },
    },
    # --- Network ---
    {
        "name": "list_network_devices",
        "description": "List all tracked network devices and their online/offline status.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_network_device",
        "description": "Add a device to the network monitor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Friendly name, e.g. 'Living Room Pico'",
                },
                "hostname": {
                    "type": "string",
                    "description": "Hostname or IP, e.g. 'pico-w-1.local' or '10.0.0.50'",
                },
            },
            "required": ["name", "hostname"],
        },
    },
    # --- System Monitor ---
    {
        "name": "get_system_status",
        "description": "Get current system status: CPU usage, memory, disk, temperature, uptime. Use when user asks about system health, performance, or resource usage.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # --- Quote ---
    {
        "name": "get_daily_quote",
        "description": "Get today's inspirational quote. Use when user asks for a quote, inspiration, or motivation.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Filtering — keyword-based tool selection for local LLM performance
# ---------------------------------------------------------------------------

# Map tool names to their group
TOOL_GROUPS: dict[str, list[str]] = {
    "weather": ["get_current_weather", "get_weather_forecast"],
    "news": ["get_news_headlines", "search_news"],
    "orders": ["get_orders", "refresh_orders"],
    "grocery": [
        "grocery_add", "grocery_list", "grocery_remove", "grocery_clear",
        "grocery_find", "grocery_stores", "grocery_price", "grocery_preference",
        "grocery_prices",
    ],
    "timers": ["timer_set", "timer_list", "timer_cancel"],
    "tasks": [
        "task_add", "task_list", "task_complete",
        "task_delete", "task_update", "task_suggest",
    ],
    "notes": ["note_add", "note_list"],
    "calendar": ["get_calendar_events", "add_calendar_event"],
    "network": ["list_network_devices", "add_network_device"],
    "system": ["get_system_status"],
    "quote": ["get_daily_quote"],
}

# Keywords that trigger each tool group
GROUP_KEYWORDS: dict[str, list[str]] = {
    "weather": [
        "weather", "temperature", "forecast", "rain", "snow", "sunny",
        "cloudy", "hot", "cold", "humid", "wind", "outside",
    ],
    "news": [
        "news", "headlines", "article", "happening", "current events",
        "breaking", "top stories",
    ],
    "orders": [
        "order", "amazon", "delivery", "package", "tracking", "shipped",
    ],
    "grocery": [
        "grocery", "groceries", "shopping", "buy", "store", "price",
        "costco", "safeway", "target", "sprouts", "whole foods",
        "india bazaar", "apna mandi", "india cash", "lucky",
        "shopping list", "add to list",
    ],
    "timers": [
        "timer", "alarm", "countdown", "minutes timer", "set timer",
        "how long", "cooking timer",
    ],
    "tasks": [
        "task", "todo", "to-do", "to do", "remind", "reminder",
        "schedule", "priority", "overdue", "stale", "due date",
        "prioritize", "what should i do",
    ],
    "notes": [
        "note", "remember that", "save that", "jot down", "write down",
    ],
    "calendar": [
        "calendar", "event", "meeting", "schedule", "appointment",
        "busy", "free time", "what do i have",
    ],
    "network": [
        "network", "device", "ping", "online", "offline", "connected",
        "pico", "mac mini",
    ],
    "system": [
        "system", "cpu", "memory", "ram", "disk", "uptime",
        "system status", "how is the pi", "pi health",
    ],
    "quote": [
        "quote", "inspiration", "motivation", "motivate", "inspire",
        "daily quote", "words of wisdom",
    ],
}

# Compound triggers — multi-group requests
COMPOUND_KEYWORDS: dict[str, list[str]] = {
    "daily brief": ["weather", "tasks", "calendar", "grocery"],
    "summary": ["weather", "tasks", "calendar", "grocery"],
    "good morning": ["weather", "tasks", "calendar", "quote"],
    "brief": ["weather", "tasks", "calendar"],
}

# Build a lookup from tool name to definition for fast filtering
_TOOL_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOOL_DEFINITIONS}


def filter_tools(user_message: str) -> list[dict]:
    """Select relevant tool definitions based on the user's message.

    Returns a subset of TOOL_DEFINITIONS matching keyword groups found in the
    message. If no keywords match, returns all tools (fallback for ambiguous
    or general-knowledge requests).
    """
    msg_lower = user_message.lower()

    matched_groups: set[str] = set()

    # Check compound keywords first (multi-group triggers)
    for keyword, groups in COMPOUND_KEYWORDS.items():
        if keyword in msg_lower:
            matched_groups.update(groups)

    # Check individual group keywords
    for group, keywords in GROUP_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                matched_groups.add(group)
                break

    # No matches → general question, no tools needed (let model answer directly)
    # OR ambiguous → send all tools
    if not matched_groups:
        # Heuristic: if it looks like a question/command that might need tools,
        # send all tools. If it's conversational, send none.
        action_hints = [
            "what", "how", "check", "show", "list", "get", "set", "add",
            "remove", "delete", "create", "tell me", "give me",
        ]
        if any(hint in msg_lower for hint in action_hints):
            return TOOL_DEFINITIONS
        return []  # Pure conversation — no tools needed

    # Collect tool definitions for matched groups
    tool_names: set[str] = set()
    for group in matched_groups:
        tool_names.update(TOOL_GROUPS.get(group, []))

    return [_TOOL_BY_NAME[name] for name in tool_names if name in _TOOL_BY_NAME]

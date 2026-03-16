TOOL_DEFINITIONS = [
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
]

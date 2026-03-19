from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import Settings
from .base import BaseService
from .cache import CacheService

logger = logging.getLogger(__name__)


class CalendarService(BaseService):
    """Calendar events from Google Calendar and/or iCloud CalDAV."""

    name = "calendar"

    def __init__(self, cache: CacheService, settings: Settings):
        self.cache = cache
        self.settings = settings
        self._google_creds_path = settings.google_calendar_credentials_json
        self._google_token_path = settings.google_calendar_token_path
        self._icloud_email = settings.icloud_caldav_email
        self._icloud_password = settings.icloud_caldav_password
        self.cache_ttl = settings.calendar_cache_ttl

    async def get_events(self, days: int = 7) -> list[dict]:
        """Fetch events from all configured sources, merged and sorted."""
        cache_key = f"calendar:events:{days}"
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        tasks = []
        if self._google_creds_path or Path(self._google_token_path).exists():
            tasks.append(self._fetch_google_events(days))
        if self._icloud_email and self._icloud_password:
            tasks.append(self._fetch_icloud_events(days))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        events = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Calendar source failed: %s", r)
            else:
                events.extend(r)

        # Sort by start time
        events.sort(key=lambda e: e.get("start", ""))

        await self.cache.set(cache_key, events, self.cache_ttl)
        return events

    async def add_event(self, summary: str, start: str, end: str, description: str = "") -> dict:
        """Add event to Google Calendar."""
        if not self._google_creds_path and not Path(self._google_token_path).exists():
            return {"error": "Google Calendar not configured"}

        def _add():
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            import json

            token_path = Path(self._google_token_path)
            if not token_path.exists():
                return {"error": "Google token not found. Run: python -m piassistant auth-google"}

            creds = Credentials.from_authorized_user_info(json.loads(token_path.read_text()))
            service = build("calendar", "v3", credentials=creds)

            event_body = {
                "summary": summary,
                "start": {"dateTime": start, "timeZone": "UTC"},
                "end": {"dateTime": end, "timeZone": "UTC"},
            }
            if description:
                event_body["description"] = description

            result = service.events().insert(calendarId="primary", body=event_body).execute()
            return {"id": result.get("id"), "summary": summary, "start": start, "end": end}

        try:
            result = await asyncio.to_thread(_add)
            # Invalidate cache
            await self.cache.invalidate("calendar:events:7")
            return result
        except Exception as e:
            logger.error("Failed to add calendar event: %s", e)
            return {"error": str(e)}

    async def _fetch_google_events(self, days: int) -> list[dict]:
        """Fetch from Google Calendar API."""
        def _fetch():
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            import json

            token_path = Path(self._google_token_path)
            if not token_path.exists():
                return []

            creds = Credentials.from_authorized_user_info(json.loads(token_path.read_text()))
            service = build("calendar", "v3", credentials=creds)

            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days)).isoformat()

            result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            ).execute()

            events = []
            for item in result.get("items", []):
                start = item.get("start", {})
                end = item.get("end", {})
                all_day = "date" in start
                events.append({
                    "summary": item.get("summary", "Untitled"),
                    "start": start.get("date") or start.get("dateTime", ""),
                    "end": end.get("date") or end.get("dateTime", ""),
                    "all_day": all_day,
                    "source": "google",
                    "calendar_name": "Primary",
                })
            return events

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.warning("Google Calendar fetch failed: %s", e)
            return []

    async def _fetch_icloud_events(self, days: int) -> list[dict]:
        """Fetch from iCloud via CalDAV."""
        def _fetch():
            import caldav

            client = caldav.DAVClient(
                url="https://caldav.icloud.com",
                username=self._icloud_email,
                password=self._icloud_password,
            )
            principal = client.principal()
            calendars = principal.calendars()

            now = datetime.now(timezone.utc)
            end = now + timedelta(days=days)

            events = []
            for cal in calendars:
                cal_name = cal.name or "iCloud"
                try:
                    results = cal.search(
                        start=now,
                        end=end,
                        event=True,
                        expand=True,
                    )
                except Exception:
                    continue

                for event in results:
                    try:
                        vevent = event.vobject_instance.vevent
                        dtstart = vevent.dtstart.value
                        dtend = getattr(vevent, "dtend", None)

                        all_day = not hasattr(dtstart, "hour")

                        if all_day:
                            start_str = str(dtstart)
                            end_str = str(dtend.value) if dtend else start_str
                        else:
                            if hasattr(dtstart, "isoformat"):
                                start_str = dtstart.isoformat()
                            else:
                                start_str = str(dtstart)
                            if dtend and hasattr(dtend.value, "isoformat"):
                                end_str = dtend.value.isoformat()
                            else:
                                end_str = start_str

                        events.append({
                            "summary": str(vevent.summary.value) if hasattr(vevent, "summary") else "Untitled",
                            "start": start_str,
                            "end": end_str,
                            "all_day": all_day,
                            "source": "icloud",
                            "calendar_name": cal_name,
                        })
                    except Exception as e:
                        logger.debug("Skipping iCloud event: %s", e)
                        continue

            return events

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.warning("iCloud Calendar fetch failed: %s", e)
            return []

    async def health_check(self) -> dict:
        sources = []
        if self._google_creds_path or Path(self._google_token_path).exists():
            sources.append("Google")
        if self._icloud_email and self._icloud_password:
            sources.append("iCloud")
        if not sources:
            return {"healthy": True, "details": "No calendar sources configured"}
        return {"healthy": True, "details": f"Sources: {', '.join(sources)}"}

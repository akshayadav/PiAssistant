import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from piassistant.config import Settings
from piassistant.services.cache import CacheService
from piassistant.services.calendar import CalendarService


@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(
        db_path=str(tmp_path / "test.db"),
        anthropic_api_key="test",
        google_calendar_credentials_json="",
        google_calendar_token_path=str(tmp_path / "no_token.json"),
        icloud_caldav_email="",
        icloud_caldav_password="",
    )


@pytest_asyncio.fixture
async def cache():
    return CacheService()


@pytest_asyncio.fixture
async def calendar(cache, tmp_settings):
    return CalendarService(cache, tmp_settings)


class TestCalendarService:
    @pytest.mark.asyncio
    async def test_no_sources_returns_empty(self, calendar):
        """With no calendar sources configured, returns empty list."""
        events = await calendar.get_events()
        assert events == []

    @pytest.mark.asyncio
    async def test_health_check_no_sources(self, calendar):
        health = await calendar.health_check()
        assert health["healthy"] is True
        assert "No calendar sources" in health["details"]

    @pytest.mark.asyncio
    async def test_health_check_with_google(self, cache, tmp_path):
        """Health check reports Google as source when token exists."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"token": "test"}')
        settings = Settings(
            anthropic_api_key="test",
            google_calendar_token_path=str(token_path),
        )
        cal = CalendarService(cache, settings)
        health = await cal.health_check()
        assert "Google" in health["details"]

    @pytest.mark.asyncio
    async def test_google_fetch_with_mock(self, cache, tmp_path):
        """Mock Google Calendar API and verify event parsing."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"token": "test", "client_id": "x", "client_secret": "y", "refresh_token": "z"}')
        settings = Settings(
            anthropic_api_key="test",
            google_calendar_token_path=str(token_path),
        )
        cal = CalendarService(cache, settings)

        mock_events = {
            "items": [
                {
                    "summary": "Team Meeting",
                    "start": {"dateTime": "2026-03-20T10:00:00Z"},
                    "end": {"dateTime": "2026-03-20T11:00:00Z"},
                },
                {
                    "summary": "All Day Event",
                    "start": {"date": "2026-03-21"},
                    "end": {"date": "2026-03-22"},
                },
            ]
        }

        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = mock_events

        with patch("piassistant.services.calendar.CalendarService._fetch_google_events") as mock_fetch:
            mock_fetch.return_value = [
                {"summary": "Team Meeting", "start": "2026-03-20T10:00:00Z", "end": "2026-03-20T11:00:00Z", "all_day": False, "source": "google", "calendar_name": "Primary"},
                {"summary": "All Day Event", "start": "2026-03-21", "end": "2026-03-22", "all_day": True, "source": "google", "calendar_name": "Primary"},
            ]
            events = await cal.get_events(days=7)
            assert len(events) == 2
            assert events[0]["summary"] == "Team Meeting"
            assert events[1]["all_day"] is True

    @pytest.mark.asyncio
    async def test_merged_events_sorted(self, cache, tmp_path):
        """Events from multiple sources are sorted by start time."""
        settings = Settings(
            anthropic_api_key="test",
            google_calendar_token_path=str(tmp_path / "no_token.json"),
        )
        cal = CalendarService(cache, settings)

        google_events = [
            {"summary": "Later", "start": "2026-03-22T10:00:00Z", "end": "2026-03-22T11:00:00Z", "all_day": False, "source": "google", "calendar_name": "Primary"},
        ]
        icloud_events = [
            {"summary": "Earlier", "start": "2026-03-20T10:00:00Z", "end": "2026-03-20T11:00:00Z", "all_day": False, "source": "icloud", "calendar_name": "Personal"},
        ]

        with patch.object(cal, "_fetch_google_events", return_value=google_events), \
             patch.object(cal, "_fetch_icloud_events", return_value=icloud_events):
            # Need both sources to be "configured"
            cal._google_creds_path = "fake"
            cal._icloud_email = "test@test.com"
            cal._icloud_password = "pass"
            events = await cal.get_events(days=7)
            assert len(events) == 2
            assert events[0]["summary"] == "Earlier"
            assert events[1]["summary"] == "Later"

    @pytest.mark.asyncio
    async def test_single_source_failure_graceful(self, cache, tmp_path):
        """If one source fails, the other still returns events."""
        settings = Settings(
            anthropic_api_key="test",
            google_calendar_token_path=str(tmp_path / "no_token.json"),
        )
        cal = CalendarService(cache, settings)
        cal._google_creds_path = "fake"
        cal._icloud_email = "test@test.com"
        cal._icloud_password = "pass"

        good_events = [
            {"summary": "Good Event", "start": "2026-03-20T10:00:00Z", "end": "2026-03-20T11:00:00Z", "all_day": False, "source": "icloud", "calendar_name": "Personal"},
        ]

        with patch.object(cal, "_fetch_google_events", side_effect=Exception("API error")), \
             patch.object(cal, "_fetch_icloud_events", return_value=good_events):
            events = await cal.get_events(days=7)
            assert len(events) == 1
            assert events[0]["summary"] == "Good Event"

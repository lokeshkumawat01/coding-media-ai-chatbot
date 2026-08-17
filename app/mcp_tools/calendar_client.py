"""
Google Calendar API client using a service account.
The service account must be shared with the target calendar
(see setup steps followed during Chunk 6 configuration).

Note: google-api-python-client is synchronous, so all calls here
are wrapped with asyncio.to_thread() when used from async MCP tools.

Timezone: all times are treated as Asia/Kolkata (IST, UTC+5:30),
matching the timezone used when creating calendar events. The
freebusy query must use the same offset, not naive UTC ("Z"),
or busy/available slot calculations will be incorrect.
"""

import json
import tempfile
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from typing import List, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import settings
from app.utils.logger import logger

SCOPES = ["https://www.googleapis.com/auth/calendar"]

IST = ZoneInfo("Asia/Kolkata")

# Business hours for slot generation (24-hour format, IST)
BUSINESS_START_HOUR = 10
BUSINESS_END_HOUR = 18
SLOT_DURATION_MINUTES = 30

def _get_credentials():
    """
    Loads Google service account credentials either from a JSON file path
    (local development) or from a JSON string in an environment variable
    (production deployments like Render, where uploading a file isn't
    practical — the JSON content is written to a temp file at runtime).
    """
    if settings.google_calendar_credentials_json:
        temp_path = os.path.join(tempfile.gettempdir(), "google_calendar_service_account.json")
        with open(temp_path, "w") as f:
            f.write(settings.google_calendar_credentials_json)
        return service_account.Credentials.from_service_account_file(temp_path, scopes=SCOPES)
    else:
        return service_account.Credentials.from_service_account_file(
            settings.google_calendar_credentials_path, scopes=SCOPES
        )


_credentials = _get_credentials()
_calendar_service = build("calendar", "v3", credentials=_credentials)


def _get_busy_slots(date: datetime) -> List[Dict[str, datetime]]:
    """
    Query Google Calendar's freebusy endpoint for the given date
    and return a list of busy {start, end} datetime ranges, in IST.
    """
    day_start = datetime.combine(date.date(), time(0, 0), tzinfo=IST)
    day_end = datetime.combine(date.date(), time(23, 59), tzinfo=IST)

    body = {
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "items": [{"id": settings.google_calendar_id}],
    }

    response = _calendar_service.freebusy().query(body=body).execute()
    busy_raw = response["calendars"][settings.google_calendar_id]["busy"]

    busy_slots = []
    for slot in busy_raw:
        start = datetime.fromisoformat(slot["start"]).astimezone(IST)
        end = datetime.fromisoformat(slot["end"]).astimezone(IST)
        busy_slots.append({"start": start, "end": end})

    return busy_slots


def get_available_slots_sync(date: datetime) -> List[str]:
    """
    Generate available 30-minute slots for a given date within business
    hours, excluding slots that overlap with existing calendar events
    AND excluding slots that have already passed if the date is today.
    Returns a list of human-readable time strings, e.g. "10:00 AM".
    """
    busy_slots = _get_busy_slots(date)
    now_ist = datetime.now(IST)
    is_today = date.date() == now_ist.date()

    slots = []
    current = datetime.combine(date.date(), time(BUSINESS_START_HOUR, 0), tzinfo=IST)
    end_of_day = datetime.combine(date.date(), time(BUSINESS_END_HOUR, 0), tzinfo=IST)

    while current < end_of_day:
        slot_end = current + timedelta(minutes=SLOT_DURATION_MINUTES)

        is_busy = any(
            current < busy["end"] and slot_end > busy["start"] for busy in busy_slots
        )

        is_past = is_today and current <= now_ist

        if not is_busy and not is_past:
            slots.append(current.strftime("%I:%M %p"))

        current = slot_end

    return slots


def book_meeting_sync(
    date: datetime,
    time_str: str,
    client_name: str,
    client_phone: str,
    topic: str,
) -> dict:
    """
    Book a 30-minute meeting on the calendar at the given date and time.
    Returns a dict with the event's link and its Google event ID.
    """
    start_time = datetime.combine(
        date.date(), datetime.strptime(time_str, "%I:%M %p").time(), tzinfo=IST
    )
    end_time = start_time + timedelta(minutes=SLOT_DURATION_MINUTES)

    event = {
        "summary": f"Consultation: {client_name} ({topic})",
        "description": f"Client phone: {client_phone}\nTopic: {topic}\nBooked via chatbot.",
        "start": {"dateTime": start_time.isoformat()},
        "end": {"dateTime": end_time.isoformat()},
    }

    created_event = (
        _calendar_service.events()
        .insert(calendarId=settings.google_calendar_id, body=event)
        .execute()
    )

    logger.info(f"Meeting booked: {created_event.get('htmlLink')}")
    return {
        "link": created_event.get("htmlLink", ""),
        "event_id": created_event.get("id", ""),
    }


def cancel_event_sync(event_id: str) -> None:
    """Delete a calendar event by its Google event ID."""
    try:
        _calendar_service.events().delete(
            calendarId=settings.google_calendar_id, eventId=event_id
        ).execute()
    except Exception as e:
        logger.warning(
            f"Could not delete calendar event {event_id} (may already be gone): {e}"
        )

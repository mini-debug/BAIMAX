import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import argparse
import httpx
import uvicorn

# Google API imports
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

# -------- Google Calendar auth/helpers --------
# Choose scopes:
# - read only: ["https://www.googleapis.com/auth/calendar.readonly"]
# - read/write: ["https://www.googleapis.com/auth/calendar"]
SCOPES = ["https://www.googleapis.com/auth/calendar"]

CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
TZ = os.getenv("TZ", "UTC")

CRED_FILE = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")  # OAuth client from Google Cloud
TOKEN_FILE = os.getenv("GOOGLE_TOKEN", "token.json")             # created on first auth

def _get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # lazy import; but Request is not strictly needed for desktop refresh if token fresh
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CRED_FILE, SCOPES)
            # launches a local server to complete OAuth in your browser
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

# -------- MCP server & tools --------
mcp = FastMCP(name="gcal", json_response=False, stateless_http=False)

@mcp.tool()
async def gcal_list(
    q: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    List events in Google Calendar. ISO 8601 for time_min/time_max (e.g., '2025-09-13T00:00:00-07:00').
    q: optional free-text search
    """
    svc = _get_service()
    params = {
        "calendarId": CALENDAR_ID,
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max(1, min(max_results, 2500)),
    }
    if q: params["q"] = q
    if time_min: params["timeMin"] = time_min
    if time_max: params["timeMax"] = time_max
    if "timeMin" not in params and "timeMax" not in params:
        # default: next 7 days
        now = datetime.now(timezone.utc)
        params["timeMin"] = now.isoformat()
        params["timeMax"] = (now + timedelta(days=7)).isoformat()

    resp = svc.events().list(**params).execute()
    events = resp.get("items", [])
    out = []
    for e in events:
        start = e.get("start", {})
        end = e.get("end", {})
        out.append({
            "id": e.get("id"),
            "summary": e.get("summary"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "location": e.get("location"),
            "status": e.get("status"),
            "hangoutLink": e.get("hangoutLink"),
        })
    return out

@mcp.tool()
async def gcal_create(
    summary: str,
    start_iso: str,
    end_iso: str,
    location: Optional[str] = None,
    description: Optional[str] = None,
    attendees: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create an event in Google Calendar. Provide start_iso/end_iso as ISO strings with timezone,
    e.g. '2025-09-13T15:00:00-07:00'.
    """
    svc = _get_service()
    body = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": TZ},
        "end":   {"dateTime": end_iso,   "timeZone": TZ},
    }
    if location: body["location"] = location
    if description: body["description"] = description
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]

    created = svc.events().insert(calendarId=CALENDAR_ID, body=body).execute()
    return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}

@mcp.tool()
async def gcal_delete(event_id: str) -> str:
    """Delete an event in Google Calendar by id."""
    svc = _get_service()
    svc.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    return f"deleted {event_id}"

@mcp.tool()
async def gcal_calendars() -> List[Dict[str, Any]]:
    """List your Google calendars (id + summary)."""
    svc = _get_service()
    resp = svc.calendarList().list().execute()
    return [{"id": c.get("id"), "summary": c.get("summary")} for c in resp.get("items", [])]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MCP Streamable HTTP based server")
    parser.add_argument("--port", type=int, default=8123, help="Localhost port to listen on")
    args = parser.parse_args()

    # Start the server with Streamable HTTP transport
    uvicorn.run(mcp.streamable_http_app, host="localhost", port=args.port)

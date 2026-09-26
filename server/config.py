"""Settings, read from environment variables or a .env file in the project root."""
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

# Server-side key for Places API (New) and Routes API. Never sent to the browser.
MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
# Browser key for the Maps JavaScript API. Restrict it to your site's URLs.
MAPS_BROWSER_KEY = os.getenv("GOOGLE_MAPS_BROWSER_KEY", "")
MAP_ID = os.getenv("GOOGLE_MAPS_MAP_ID", "DEMO_MAP_ID")

LANGUAGE = os.getenv("LANGUAGE", "en")


def missing_keys() -> list[str]:
    out = []
    if not GEMINI_API_KEY:
        out.append("GEMINI_API_KEY")
    if not MAPS_KEY:
        out.append("GOOGLE_MAPS_API_KEY")
    return out

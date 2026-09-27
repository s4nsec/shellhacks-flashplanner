"""Settings, read from environment variables or a .env file in the project root."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Without a key, set GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT and
# GOOGLE_CLOUD_LOCATION to call Gemini on Vertex AI with application default
# credentials (gcloud auth application-default login). The SDK reads these itself.
USE_VERTEX = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Server-side key for Places API (New) and Routes API. Never sent to the browser.
MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
# Browser key for the Maps JavaScript API. Restrict it to your site's URLs.
MAPS_BROWSER_KEY = os.getenv("GOOGLE_MAPS_BROWSER_KEY", "")
MAP_ID = os.getenv("GOOGLE_MAPS_MAP_ID", "DEMO_MAP_ID")

LANGUAGE = os.getenv("LANGUAGE", "en")


def missing_keys() -> list[str]:
    out = []
    if not GEMINI_API_KEY and not USE_VERTEX:
        out.append("GEMINI_API_KEY")
    if not MAPS_KEY:
        out.append("GOOGLE_MAPS_API_KEY")
    return out

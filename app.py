"""Vercel entrypoint: Vercel looks for a FastAPI `app` in ./app.py."""
from server.main import app  # noqa: F401

"""Check that GEMINI_API_KEY works. Run from the project root:

    python -m server.check_gemini
"""
import sys

from google import genai

try:
    from . import config
except ImportError:  # run as a file: python3 server/check_gemini.py
    import config

if not config.GEMINI_API_KEY:
    sys.exit("GEMINI_API_KEY is not set (check your .env).")

client = genai.Client(api_key=config.GEMINI_API_KEY)
try:
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL, contents="Reply with the single word: ok"
    )
except Exception as e:
    sys.exit(f"FAILED with model {config.GEMINI_MODEL}: {e}")

print(f"OK: model {config.GEMINI_MODEL} replied: {resp.text.strip()}")

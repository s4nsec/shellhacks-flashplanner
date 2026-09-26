"""SQLite recipes for rebuilding sessions without storing Google Places content.

Only user-supplied trip settings and live actions are written to disk. A restored
session is rebuilt with fresh Places, Routes, Weather, and Gemini calls.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(os.getenv("SESSION_DB_PATH", "sessions.sqlite3"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS session_recipes (
            id TEXT PRIMARY KEY,
            trip_json TEXT NOT NULL,
            actions_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            touched_at REAL NOT NULL
        )
    """)
    return db


@contextmanager
def _db():
    db = _connect()
    try:
        yield db
        db.commit()
    finally:
        db.close()


def save(session_id: str, trip: dict, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _db() as db:
        db.execute(
            "INSERT OR REPLACE INTO session_recipes VALUES (?, ?, ?, ?, ?)",
            (session_id, json.dumps(trip, ensure_ascii=False), "[]", now, now),
        )


def load(session_id: str, ttl_seconds: int, now: float | None = None) -> dict | None:
    now = time.time() if now is None else now
    with _db() as db:
        row = db.execute(
            "SELECT trip_json, actions_json, touched_at FROM session_recipes WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        if row[2] < now - ttl_seconds:
            db.execute("DELETE FROM session_recipes WHERE id = ?", (session_id,))
            return None
        db.execute("UPDATE session_recipes SET touched_at = ? WHERE id = ?", (now, session_id))
    return {"trip": json.loads(row[0]), "actions": json.loads(row[1])}


def append_action(session_id: str, action: dict, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _db() as db:
        row = db.execute(
            "SELECT actions_json FROM session_recipes WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return
        actions = json.loads(row[0])
        actions.append(action)
        db.execute(
            "UPDATE session_recipes SET actions_json = ?, touched_at = ? WHERE id = ?",
            (json.dumps(actions, ensure_ascii=False), now, session_id),
        )


def touch(session_id: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _db() as db:
        db.execute("UPDATE session_recipes SET touched_at = ? WHERE id = ?", (now, session_id))


def purge_expired(ttl_seconds: int, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _db() as db:
        db.execute("DELETE FROM session_recipes WHERE touched_at < ?", (now - ttl_seconds,))

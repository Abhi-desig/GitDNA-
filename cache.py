"""SQLite cache for normalized events.

Stores the GitEvent list rather than GitHub's raw JSON: it is an order of
magnitude smaller (a 400-repo account's raw payload is megabytes), and it is the
stable interface the rest of the pipeline actually consumes. The tradeoff is
that changing how events are built invalidates the cache -- hence SCHEMA_VERSION,
which is compared on read so a bump silently refreshes everyone.

stdlib sqlite3, no ORM, no server. Calls are synchronous and therefore block the
event loop, which is fine at these sizes (single-row reads of a few hundred KB)
and is not worth an async driver.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from models import GitEvent

# Deploys mount a volume and point GITDNA_DB at it, so the cache survives
# restarts; locally it just sits next to the code.
DB_PATH = Path(os.environ.get("GITDNA_DB") or Path(__file__).with_name("gitdna.db"))
TTL_SECONDS = 6 * 3600
SCHEMA_VERSION = 1  # bump when events.py changes shape


@dataclass
class Cached:
    login: str
    events: list[GitEvent]
    age: float  # seconds since fetch

    @property
    def fresh(self) -> bool:
        return self.age < TTL_SECONDS


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "  key TEXT PRIMARY KEY,"
        "  login TEXT NOT NULL,"
        "  version INTEGER NOT NULL,"
        "  events TEXT NOT NULL,"
        "  fetched_at REAL NOT NULL)"
    )
    return conn


def load(login: str) -> Cached | None:
    """Return whatever is cached, fresh or not. Callers decide via .fresh.

    Staleness is deliberately the caller's problem: a stale entry is worthless
    on a normal request but is the best possible answer when GitHub is refusing
    to talk to us.
    """
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT login, events, fetched_at FROM cache WHERE key = ? AND version = ?",
                (login.lower(), SCHEMA_VERSION),
            ).fetchone()
    except (sqlite3.Error, OSError):
        # A broken cache must never take the site down: an unwritable path
        # raises OSError from mkdir/connect, not sqlite3.Error.
        return None

    if row is None:
        return None

    resolved, blob, fetched_at = row
    try:
        events = [GitEvent.from_json(item) for item in json.loads(blob)]
    except (ValueError, KeyError):
        return None
    return Cached(login=resolved, events=events, age=max(0.0, time.time() - fetched_at))


def save(login: str, resolved: str, events: list[GitEvent]) -> None:
    blob = json.dumps([event.to_json() for event in events])
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO cache (key, login, version, events, fetched_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "login=excluded.login, version=excluded.version, "
                "events=excluded.events, fetched_at=excluded.fetched_at",
                (login.lower(), resolved, SCHEMA_VERSION, blob, time.time()),
            )
    except (sqlite3.Error, OSError):
        pass  # caching is an optimization, never a hard dependency

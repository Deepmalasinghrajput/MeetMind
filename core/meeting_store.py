"""SQLite persistence for processed meetings (history dashboard)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "meetings.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                source TEXT,
                language TEXT,
                transcript TEXT,
                transcript_segments TEXT,
                summary TEXT,
                action_items TEXT,
                key_decisions TEXT,
                open_questions TEXT,
                word_count INTEGER DEFAULT 0,
                segment_count INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        # Migrate older DBs that predate user_id
        cols = {r[1] for r in conn.execute("PRAGMA table_info(meetings)").fetchall()}
        if "user_id" not in cols:
            conn.execute("ALTER TABLE meetings ADD COLUMN user_id INTEGER")
        conn.commit()


def save_meeting(payload: dict[str, Any]) -> int:
    init_db()
    segments = payload.get("segments") or []
    created = datetime.now(timezone.utc).isoformat()
    duration = 0.0
    if segments:
        try:
            duration = float(segments[-1].get("end") or 0)
        except (TypeError, ValueError, IndexError):
            duration = 0.0

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO meetings (
                user_id, title, source, language, transcript, transcript_segments,
                summary, action_items, key_decisions, open_questions,
                word_count, segment_count, duration_seconds, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("user_id"),
                payload.get("title") or "Untitled Meeting",
                payload.get("source") or "",
                payload.get("language") or "english",
                payload.get("transcript") or "",
                json.dumps(segments),
                payload.get("summary") or "",
                payload.get("action_items") or "",
                payload.get("key_decisions") or "",
                payload.get("open_questions") or "",
                int(payload.get("word_count") or 0),
                len(segments),
                duration,
                created,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_meetings(user_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        if user_id is None:
            rows = conn.execute(
                """
                SELECT id, title, source, language, word_count, segment_count,
                       duration_seconds, created_at
                FROM meetings
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, source, language, word_count, segment_count,
                       duration_seconds, created_at
                FROM meetings
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def get_meeting(meeting_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        if user_id is None:
            row = conn.execute(
                "SELECT * FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM meetings WHERE id = ? AND user_id = ?",
                (meeting_id, user_id),
            ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["segments"] = json.loads(data.pop("transcript_segments") or "[]")
    except json.JSONDecodeError:
        data["segments"] = []
    return data


def delete_meeting(meeting_id: int, user_id: int | None = None) -> bool:
    init_db()
    with _connect() as conn:
        if user_id is None:
            cur = conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        else:
            cur = conn.execute(
                "DELETE FROM meetings WHERE id = ? AND user_id = ?",
                (meeting_id, user_id),
            )
        conn.commit()
        return cur.rowcount > 0

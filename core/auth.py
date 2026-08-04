"""User authentication (register, login, password hashing)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "meetings.db"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_credentials(name: str, email: str, password: str, *, is_register: bool) -> str | None:
    email = normalize_email(email)
    password = password or ""
    if not email or not _EMAIL_RE.match(email):
        return "Enter a valid email address."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    if is_register:
        name = (name or "").strip()
        if len(name) < 2:
            return "Enter your name (at least 2 characters)."
        if len(name) > 80:
            return "Name is too long."
    return None


def create_user(name: str, email: str, password: str) -> tuple[dict[str, Any] | None, str | None]:
    init_users_db()
    email = normalize_email(email)
    name = (name or "").strip()
    if not name and email:
        # Allow register without name — use email local-part
        name = email.split("@")[0].replace(".", " ").replace("_", " ").strip() or "User"
    if len(name) == 1:
        name = name + "."

    err = validate_credentials(name, email, password, is_register=True)
    if err:
        return None, err

    created = datetime.now(timezone.utc).isoformat()
    try:
        pw_hash = generate_password_hash(password)
    except Exception as exc:
        return None, f"Could not hash password: {exc}"

    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, name, pw_hash, created),
            )
            conn.commit()
            user_id = int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None, "An account with this email already exists. Try signing in instead."
    except sqlite3.Error as exc:
        return None, f"Database error while creating account: {exc}"

    if not user_id:
        return None, "Account was not created. Please try again."

    return {"id": user_id, "email": email, "name": name}, None


def authenticate_user(email: str, password: str) -> tuple[dict[str, Any] | None, str | None]:
    init_users_db()
    err = validate_credentials("", email, password, is_register=False)
    if err:
        return None, err

    email = normalize_email(email)
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, name, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
        return None, "Invalid email or password."

    return {
        "id": int(row["id"]),
        "email": row["email"],
        "name": row["name"],
    }, None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    init_users_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {"id": int(row["id"]), "email": row["email"], "name": row["name"]}

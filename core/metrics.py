"""Lightweight usage and performance metrics stored in SQLite."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "meetings.db"
JSON_LOG_PATH = BASE_DIR / "data" / "metrics.jsonl"

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_metrics_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS request_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                duration_ms REAL NOT NULL,
                user_id INTEGER,
                success INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                stage TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                user_id INTEGER,
                meeting_id INTEGER,
                success INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_name TEXT NOT NULL,
                user_id INTEGER
            )
            """
        )
        conn.commit()


def _append_json_log(record: dict[str, Any]) -> None:
    try:
        JSON_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with JSON_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        logger.debug("Could not write metrics JSON log: %s", exc)


def log_request(
    path: str,
    method: str,
    status_code: int,
    duration_ms: float,
    user_id: int | None = None,
) -> None:
    init_metrics_db()
    success = 1 if status_code < 400 else 0
    created = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO request_events
                (created_at, path, method, status_code, duration_ms, user_id, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created, path, method, status_code, round(duration_ms, 2), user_id, success),
        )
        conn.commit()

    record = {
        "type": "request",
        "created_at": created,
        "path": path,
        "method": method,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "user_id": user_id,
        "success": bool(success),
    }
    _append_json_log(record)
    logger.info(
        "[METRICS] request %s %s -> %s in %.1fms",
        method,
        path,
        status_code,
        duration_ms,
    )


def log_pipeline_stage(
    stage: str,
    duration_ms: float,
    user_id: int | None = None,
    meeting_id: int | None = None,
    success: bool = True,
) -> None:
    init_metrics_db()
    created = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO pipeline_events
                (created_at, stage, duration_ms, user_id, meeting_id, success)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created,
                stage,
                round(duration_ms, 2),
                user_id,
                meeting_id,
                1 if success else 0,
            ),
        )
        conn.commit()

    record = {
        "type": "pipeline_stage",
        "created_at": created,
        "stage": stage,
        "duration_ms": round(duration_ms, 2),
        "user_id": user_id,
        "meeting_id": meeting_id,
        "success": success,
    }
    _append_json_log(record)
    logger.info(
        "[METRICS] pipeline %s %.1fms success=%s",
        stage,
        duration_ms,
        success,
    )


def log_event(event_name: str, user_id: int | None = None) -> None:
    init_metrics_db()
    created = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO event_log (created_at, event_name, user_id)
            VALUES (?, ?, ?)
            """,
            (created, event_name, user_id),
        )
        conn.commit()

    _append_json_log(
        {"type": "event", "created_at": created, "event_name": event_name, "user_id": user_id}
    )
    logger.info("[METRICS] event %s user_id=%s", event_name, user_id)


@contextmanager
def track_stage(
    stage: str,
    user_id: int | None = None,
    meeting_id: int | None = None,
):
    """Time a pipeline stage without changing its return value."""
    start = time.perf_counter()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log_pipeline_stage(stage, elapsed_ms, user_id=user_id, meeting_id=meeting_id, success=ok)


def _safe_scalar(conn: sqlite3.Connection, query: str, default: Any = 0) -> Any:
    try:
        row = conn.execute(query).fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]
    except sqlite3.Error:
        return default


def _stage_success_stats(conn: sqlite3.Connection, stage: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS succeeded,
               ROUND(AVG(CASE WHEN success = 1 THEN duration_ms END), 1) AS avg_ms
        FROM pipeline_events
        WHERE stage = ?
        """,
        (stage,),
    ).fetchone()
    if not row or not row["total"]:
        return {"runs": 0, "succeeded": 0, "failed": 0, "success_rate_pct": 0.0, "avg_ms": 0.0}
    total = int(row["total"])
    succeeded = int(row["succeeded"] or 0)
    failed = total - succeeded
    return {
        "runs": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate_pct": round(100.0 * succeeded / total, 1) if total else 0.0,
        "avg_ms": float(row["avg_ms"] or 0.0),
    }


def _chroma_document_count() -> int:
    chroma_path = BASE_DIR / "vector_db"
    if not chroma_path.exists():
        return 0
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(chroma_path))
        coll = client.get_collection("meeting_transcript")
        return int(coll.count())
    except Exception:
        return 0


def get_usage_stats() -> dict[str, Any]:
    """Resume-friendly usage stats: transcription, pipeline, meetings, success rates."""
    init_metrics_db()
    with _connect() as conn:
        transcription = _stage_success_stats(conn, "transcribe")
        summarization = _stage_success_stats(conn, "llm_summary")
        upload_to_summary = _stage_success_stats(conn, "upload_to_summary")
        pipeline_total = _stage_success_stats(conn, "pipeline_total")

        meetings_total = int(_safe_scalar(conn, "SELECT COUNT(*) FROM meetings", 0))
        avg_word_count = float(_safe_scalar(conn, "SELECT AVG(word_count) FROM meetings", 0.0))
        total_words = int(_safe_scalar(conn, "SELECT COALESCE(SUM(word_count), 0) FROM meetings", 0))
        max_word_count = int(_safe_scalar(conn, "SELECT COALESCE(MAX(word_count), 0) FROM meetings", 0))

    chroma_docs = _chroma_document_count()

    return {
        "meetings_processed": meetings_total,
        "chroma_documents_indexed": chroma_docs,
        "avg_transcription_seconds": round(transcription["avg_ms"] / 1000, 1),
        "avg_transcription_ms": transcription["avg_ms"],
        "transcription_runs": transcription["runs"],
        "transcription_success_rate_pct": transcription["success_rate_pct"],
        "transcription_failed": transcription["failed"],
        "avg_upload_to_summary_seconds": round(upload_to_summary["avg_ms"] / 1000, 1),
        "avg_upload_to_summary_ms": upload_to_summary["avg_ms"],
        "upload_to_summary_runs": upload_to_summary["runs"],
        "avg_pipeline_total_seconds": round(pipeline_total["avg_ms"] / 1000, 1),
        "pipeline_success_rate_pct": pipeline_total["success_rate_pct"],
        "pipeline_runs": pipeline_total["runs"],
        "pipeline_failed": pipeline_total["failed"],
        "summarization_success_rate_pct": summarization["success_rate_pct"],
        "summarization_runs": summarization["runs"],
        "summarization_failed": summarization["failed"],
        "avg_transcript_word_count": round(avg_word_count, 0),
        "total_words_processed": total_words,
        "max_transcript_word_count": max_word_count,
        "db_path": str(DB_PATH),
    }


def print_usage_stats() -> None:
    s = get_usage_stats()
    print("\n=== AI Meeting Assistant Usage Stats ===\n")
    print(f"Meetings processed:              {s['meetings_processed']}")
    print(f"ChromaDB documents indexed:    {s['chroma_documents_indexed']}")
    print()
    print(f"Avg transcription time:          {s['avg_transcription_seconds']} s  ({s['transcription_runs']} runs)")
    print(f"Transcription success rate:      {s['transcription_success_rate_pct']}%  ({s['transcription_failed']} failed)")
    print()
    print(f"Avg upload to summary time:      {s['avg_upload_to_summary_seconds']} s  ({s['upload_to_summary_runs']} runs)")
    print(f"Summarization success rate:      {s['summarization_success_rate_pct']}%  ({s['summarization_failed']} failed)")
    print()
    print(f"Avg full pipeline (end-to-end):  {s['avg_pipeline_total_seconds']} s  ({s['pipeline_runs']} runs)")
    print(f"Pipeline success rate:           {s['pipeline_success_rate_pct']}%  ({s['pipeline_failed']} failed)")
    print()
    print(f"Avg transcript length:           {s['avg_transcript_word_count']} words")
    print(f"Total words processed:           {s['total_words_processed']}")
    print(f"Largest transcript:              {s['max_transcript_word_count']} words")
    print(f"\nSource: {s['db_path']}\n")


def get_metrics_summary() -> dict[str, Any]:
    init_metrics_db()
    with _connect() as conn:
        requests_total = int(_safe_scalar(conn, "SELECT COUNT(*) FROM request_events", 0))
        requests_success = int(
            _safe_scalar(conn, "SELECT COUNT(*) FROM request_events WHERE success = 1", 0)
        )
        requests_failed = requests_total - requests_success
        avg_latency_ms = float(
            _safe_scalar(conn, "SELECT AVG(duration_ms) FROM request_events", 0.0)
        )
        unique_users_active = int(
            _safe_scalar(
                conn,
                "SELECT COUNT(DISTINCT user_id) FROM request_events WHERE user_id IS NOT NULL",
                0,
            )
        )

        stage_rows = conn.execute(
            """
            SELECT stage,
                   COUNT(*) AS runs,
                   ROUND(AVG(duration_ms), 1) AS avg_ms,
                   ROUND(MAX(duration_ms), 1) AS max_ms
            FROM pipeline_events
            GROUP BY stage
            ORDER BY avg_ms DESC
            """
        ).fetchall()
        stage_avg_ms = {row["stage"]: row["avg_ms"] for row in stage_rows}

        event_rows = conn.execute(
            """
            SELECT event_name, COUNT(*) AS count
            FROM event_log
            GROUP BY event_name
            ORDER BY count DESC
            """
        ).fetchall()
        event_counts = {row["event_name"]: row["count"] for row in event_rows}

        meetings_total = int(_safe_scalar(conn, "SELECT COUNT(*) FROM meetings", 0))
        meetings_users = int(
            _safe_scalar(
                conn,
                "SELECT COUNT(DISTINCT user_id) FROM meetings WHERE user_id IS NOT NULL",
                0,
            )
        )
        avg_word_count = float(
            _safe_scalar(conn, "SELECT AVG(word_count) FROM meetings", 0.0)
        )
        avg_duration_seconds = float(
            _safe_scalar(conn, "SELECT AVG(duration_seconds) FROM meetings", 0.0)
        )

        registered_users = int(_safe_scalar(conn, "SELECT COUNT(*) FROM users", 0))

        pipeline_total_runs = int(
            _safe_scalar(
                conn,
                "SELECT COUNT(*) FROM pipeline_events WHERE stage = 'pipeline_total'",
                0,
            )
        )
        pipeline_success = int(
            _safe_scalar(
                conn,
                """
                SELECT COUNT(*) FROM pipeline_events
                WHERE stage = 'pipeline_total' AND success = 1
                """,
                0,
            )
        )
        avg_pipeline_ms = float(
            _safe_scalar(
                conn,
                """
                SELECT AVG(duration_ms) FROM pipeline_events
                WHERE stage = 'pipeline_total' AND success = 1
                """,
                0.0,
            )
        )

    success_rate_pct = (
        round(100.0 * requests_success / requests_total, 1) if requests_total else 0.0
    )
    pipeline_success_rate_pct = (
        round(100.0 * pipeline_success / pipeline_total_runs, 1)
        if pipeline_total_runs
        else 0.0
    )

    return {
        "requests_total": requests_total,
        "requests_success": requests_success,
        "requests_failed": requests_failed,
        "success_rate_pct": success_rate_pct,
        "avg_latency_ms": round(avg_latency_ms, 1),
        "unique_users_active": unique_users_active,
        "registered_users": registered_users,
        "meetings_processed": meetings_total,
        "meetings_unique_users": meetings_users,
        "avg_word_count": round(avg_word_count, 0),
        "avg_meeting_duration_seconds": round(avg_duration_seconds, 1),
        "pipeline_runs": pipeline_total_runs,
        "pipeline_success_rate_pct": pipeline_success_rate_pct,
        "avg_pipeline_ms": round(avg_pipeline_ms, 1),
        "avg_pipeline_seconds": round(avg_pipeline_ms / 1000, 1),
        "stage_avg_ms": stage_avg_ms,
        "stage_details": [dict(r) for r in stage_rows],
        "event_counts": event_counts,
        "db_path": str(DB_PATH),
        "json_log_path": str(JSON_LOG_PATH),
    }


def print_metrics_report() -> None:
    summary = get_metrics_summary()
    print("\n=== AI Meeting Assistant Metrics Summary ===\n")
    print(f"Database: {summary['db_path']}")
    print(f"JSON log: {summary['json_log_path']}\n")

    print("--- API traffic ---")
    print(f"  Total requests:     {summary['requests_total']}")
    print(f"  Successful:         {summary['requests_success']}")
    print(f"  Failed:             {summary['requests_failed']}")
    print(f"  Success rate:       {summary['success_rate_pct']}%")
    print(f"  Avg latency:        {summary['avg_latency_ms']} ms")
    print(f"  Active users:       {summary['unique_users_active']}")
    print(f"  Registered users:   {summary['registered_users']}")

    print("\n--- Product usage ---")
    print(f"  Meetings processed: {summary['meetings_processed']}")
    print(f"  Users w/ meetings:  {summary['meetings_unique_users']}")
    print(f"  Avg words/meeting:  {summary['avg_word_count']}")
    print(f"  Avg duration (sec): {summary['avg_meeting_duration_seconds']}")

    print("\n--- Pipeline ---")
    print(f"  Total runs:         {summary['pipeline_runs']}")
    print(f"  Success rate:       {summary['pipeline_success_rate_pct']}%")
    print(f"  Avg end-to-end:     {summary['avg_pipeline_seconds']} s")

    if summary["stage_details"]:
        print("\n--- Stage timings (avg ms) ---")
        for row in summary["stage_details"]:
            print(f"  {row['stage']:<18} avg={row['avg_ms']:>8}  max={row['max_ms']:>8}  runs={row['runs']}")

    if summary["event_counts"]:
        print("\n--- Key events ---")
        for name, count in summary["event_counts"].items():
            print(f"  {name:<22} {count}")

    print()


if __name__ == "__main__":
    print_metrics_report()

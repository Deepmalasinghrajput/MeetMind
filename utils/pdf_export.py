"""Lightweight PDF export for meeting reports (fpdf2)."""

from __future__ import annotations

import io
from typing import Any


def _safe(text: str) -> str:
    """FPDF core fonts are latin-1 friendly; strip unsupported chars."""
    if not text:
        return ""
    return (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2022", "-")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def build_meeting_pdf(meeting: dict[str, Any], include: dict[str, bool] | None = None) -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError(
            "fpdf2 is required for PDF export. Run: pip install fpdf2"
        ) from exc

    include = include or {
        "title": True,
        "summary": True,
        "action_items": True,
        "key_decisions": True,
        "open_questions": True,
        "transcript": False,
    }

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)

    title = _safe(meeting.get("title") or "Meeting Report")
    if include.get("title", True):
        pdf.multi_cell(0, 10, title)
        pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    meta = []
    if meeting.get("language"):
        meta.append(f"Language: {meeting['language']}")
    if meeting.get("word_count"):
        meta.append(f"Words: {meeting['word_count']}")
    if meeting.get("duration_seconds"):
        secs = int(float(meeting["duration_seconds"]))
        meta.append(f"Duration: {secs // 60}m {secs % 60}s")
    if meta:
        pdf.multi_cell(0, 6, _safe(" | ".join(meta)))
        pdf.ln(4)

    sections = [
        ("summary", "Summary", meeting.get("summary")),
        ("action_items", "Action Items", meeting.get("action_items")),
        ("key_decisions", "Key Decisions", meeting.get("key_decisions")),
        ("open_questions", "Open Questions", meeting.get("open_questions")),
        ("transcript", "Transcript", meeting.get("transcript")),
    ]

    for key, heading, body in sections:
        if not include.get(key, False) or not body:
            continue
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(0, 8, _safe(heading))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _safe(str(body)))
        pdf.ln(3)

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()

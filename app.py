"""
MeetMind — Flask UI wrapper for the AI Meeting Intelligence pipeline.
Paste a YouTube URL (or upload a file) → transcript + AI insights + history.
"""

import os
import secrets
import tempfile
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, send_file, session
import time
import io

# Load .env from project root (next to this file)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Secure cookies on Render / HTTPS
if os.getenv("RENDER") or os.getenv("FORCE_HTTPS", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PREFERRED_URL_SCHEME"] = "https"

from datetime import timedelta
app.permanent_session_lifetime = timedelta(days=14)

_rag_chain_store: dict = {}
_active_meeting_id = None

ALLOWED_EXTENSIONS = {
    ".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg",
    ".flac", ".mkv", ".avi", ".mov",
}


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _current_user_id() -> int | None:
    uid = session.get("user_id")
    return int(uid) if uid is not None else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _current_user_id():
            return jsonify({"error": "Authentication required", "auth_required": True}), 401
        return fn(*args, **kwargs)

    return wrapper


def _check_ready() -> dict:
    """Report what is needed before Analyze Meeting can fully succeed."""
    groq = bool(os.getenv("GROQ_API_KEY", "").strip())
    try:
        import whisper  # noqa: F401
        whisper_ok = True
    except Exception as exc:
        whisper_ok = False
        whisper_err = str(exc)
    else:
        whisper_err = None

    return {
        "status": "ok" if (groq and whisper_ok) else "setup_needed",
        "groq_api_key": groq,
        "whisper": whisper_ok,
        "whisper_error": whisper_err,
        "ready": groq and whisper_ok,
        "message": (
            "Ready to process meetings."
            if (groq and whisper_ok)
            else (
                "Missing GROQ_API_KEY in .env - add it, then restart the server."
                if not groq
                else f"Whisper not available: {whisper_err}"
            )
        ),
    }


def _rebuild_rag(transcript: str) -> bool:
    from core.rag_engine import build_rag_chain

    try:
        _rag_chain_store["default"] = build_rag_chain(transcript)
        return True
    except Exception as rag_exc:
        app.logger.warning("RAG build failed: %s", rag_exc)
        return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/ready")
def ready():
    return jsonify(_check_ready())


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    from core.auth import create_user

    data = request.get_json(force=True) or {}
    user, err = create_user(
        name=data.get("name") or "",
        email=data.get("email") or "",
        password=data.get("password") or "",
    )
    if err:
        return jsonify({"error": err}), 400

    _login_session(user)
    from core.metrics import log_event

    log_event("auth_register", user_id=user["id"])
    return jsonify({"user": user})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    from core.auth import authenticate_user

    data = request.get_json(force=True) or {}
    user, err = authenticate_user(
        email=data.get("email") or "",
        password=data.get("password") or "",
    )
    if err:
        return jsonify({"error": err}), 401

    _login_session(user)
    from core.metrics import log_event

    log_event("auth_login", user_id=user["id"])
    return jsonify({"user": user})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    _rag_chain_store.pop("default", None)
    global _active_meeting_id
    _active_meeting_id = None
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    uid = _current_user_id()
    if not uid:
        return jsonify({"authenticated": False, "user": None})

    from core.auth import get_user_by_id

    user = get_user_by_id(uid)
    if not user:
        session.clear()
        return jsonify({"authenticated": False, "user": None})
    return jsonify({"authenticated": True, "user": user})


def _login_session(user: dict) -> None:
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    session.permanent = True


@app.route("/process", methods=["POST"])
@login_required
def process():
    """
    Main pipeline endpoint.
    JSON: { source: "youtube_url", language: "english"|"hinglish" }
    FormData: file=<binary>, language=<str>
    """
    ready_info = _check_ready()
    if not ready_info["whisper"]:
        return jsonify({
            "error": (
                "Whisper is not installed. Run: python -m pip install openai-whisper"
            )
        }), 503
    if not ready_info["groq_api_key"]:
        return jsonify({
            "error": (
                "GROQ_API_KEY is missing. Create a .env file in the project folder "
                "with: GROQ_API_KEY=your_key_here  then restart python app.py. "
                "Get a free key at https://console.groq.com"
            )
        }), 503

    from utils.audio_processor import process_input
    from core.transcriber import transcribe_all
    from core.summarize import summarize, generate_title
    from core.extractor import extract_action_items, extract_key_decisions, extract_questions
    from core.meeting_store import save_meeting
    from core.metrics import log_event, track_stage

    tmp_file = None
    source_label = ""
    user_id = _current_user_id()
    pipeline_start = time.perf_counter()
    pipeline_ok = False
    meeting_id = None

    try:
        if request.is_json:
            data = request.get_json(force=True) or {}
            source = (data.get("source") or "").strip()
            language = (data.get("language") or "english").strip()
            source_label = source
            if not source:
                return jsonify({"error": "No source URL provided"}), 400
        else:
            language = (request.form.get("language") or "english").strip()
            if "file" not in request.files:
                return jsonify({"error": "No file uploaded"}), 400
            upload = request.files["file"]
            if not upload.filename or not allowed_file(upload.filename):
                return jsonify({"error": "Unsupported file type"}), 400

            suffix = Path(upload.filename).suffix.lower()
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            upload.save(tmp_file.name)
            source = tmp_file.name
            source_label = upload.filename

        if language not in ("english", "hinglish"):
            language = "english"

        app.logger.info("Pipeline start | language=%s | source=%s", language, source[:80])

        with track_stage("upload_to_summary", user_id=user_id):
            with track_stage("audio_import", user_id=user_id):
                chunks = process_input(source)
            with track_stage("transcribe", user_id=user_id):
                tr = transcribe_all(chunks, language)
            transcript = tr["text"] if isinstance(tr, dict) else str(tr)
            segments = tr.get("segments", []) if isinstance(tr, dict) else []
            word_count = tr.get("word_count", 0) if isinstance(tr, dict) else len(transcript.split())
            duration_seconds = tr.get("duration_seconds", 0) if isinstance(tr, dict) else 0

            if not transcript or not transcript.strip():
                return jsonify({
                    "error": "Transcription produced empty text. Try another video or file."
                }), 500

            with track_stage("llm_title", user_id=user_id):
                title = generate_title(transcript)
            with track_stage("llm_summary", user_id=user_id):
                summary = summarize(transcript)
        with track_stage("llm_extract", user_id=user_id):
            action_items = extract_action_items(transcript)
            key_decisions = extract_key_decisions(transcript)
            open_questions = extract_questions(transcript)

        with track_stage("rag_build", user_id=user_id):
            rag_ready = _rebuild_rag(transcript)

        with track_stage("db_save", user_id=user_id):
            meeting_id = save_meeting({
                "user_id": user_id,
                "title": title,
                "source": source_label,
                "language": language,
                "transcript": transcript,
                "segments": segments,
                "summary": summary,
                "action_items": action_items,
                "key_decisions": key_decisions,
                "open_questions": open_questions,
                "word_count": word_count,
            })
        global _active_meeting_id
        _active_meeting_id = meeting_id
        pipeline_ok = True
        log_event("pipeline_success", user_id=user_id)

        return jsonify({
            "id": meeting_id,
            "title": title,
            "transcript": transcript,
            "segments": segments,
            "summary": summary,
            "action_items": action_items,
            "key_decisions": key_decisions,
            "open_questions": open_questions,
            "rag_ready": rag_ready,
            "stats": {
                "word_count": word_count,
                "segment_count": len(segments),
                "duration_seconds": duration_seconds,
                "language": language,
            },
        })

    except Exception as exc:
        log_event("pipeline_failure", user_id=user_id)
        app.logger.error("Pipeline error: %s", exc, exc_info=True)
        msg = str(exc)
        if "GROQ" in msg.upper() or "api_key" in msg.lower() or "401" in msg:
            msg = (
                f"{msg}. Check GROQ_API_KEY in your .env file and restart the server."
            )
        return jsonify({"error": msg}), 500

    finally:
        from core.metrics import log_pipeline_stage

        elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
        log_pipeline_stage(
            "pipeline_total",
            elapsed_ms,
            user_id=user_id,
            meeting_id=meeting_id,
            success=pipeline_ok,
        )
        if tmp_file and os.path.exists(tmp_file.name):
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass


@app.route("/meetings", methods=["GET"])
@login_required
def meetings_list():
    from core.meeting_store import list_meetings

    return jsonify({"meetings": list_meetings(user_id=_current_user_id())})


@app.route("/meetings/<int:meeting_id>", methods=["GET"])
@login_required
def meetings_get(meeting_id: int):
    from core.meeting_store import get_meeting

    meeting = get_meeting(meeting_id, user_id=_current_user_id())
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    # Make this meeting active for chat
    global _active_meeting_id
    _active_meeting_id = meeting_id
    rag_ready = _rebuild_rag(meeting.get("transcript") or "")

    return jsonify({
        "id": meeting["id"],
        "title": meeting["title"],
        "transcript": meeting["transcript"],
        "segments": meeting.get("segments") or [],
        "summary": meeting["summary"],
        "action_items": meeting["action_items"],
        "key_decisions": meeting["key_decisions"],
        "open_questions": meeting["open_questions"],
        "source": meeting.get("source"),
        "language": meeting.get("language"),
        "created_at": meeting.get("created_at"),
        "rag_ready": rag_ready,
        "stats": {
            "word_count": meeting.get("word_count") or 0,
            "segment_count": meeting.get("segment_count") or 0,
            "duration_seconds": meeting.get("duration_seconds") or 0,
            "language": meeting.get("language") or "english",
        },
    })


@app.route("/meetings/<int:meeting_id>", methods=["DELETE"])
@login_required
def meetings_delete(meeting_id: int):
    from core.meeting_store import delete_meeting

    ok = delete_meeting(meeting_id, user_id=_current_user_id())
    if not ok:
        return jsonify({"error": "Meeting not found"}), 404
    return jsonify({"ok": True})


@app.route("/follow-up-email", methods=["POST"])
@login_required
def follow_up_email():
    ready_info = _check_ready()
    if not ready_info["groq_api_key"]:
        return jsonify({"error": "GROQ_API_KEY is missing"}), 503

    from core.extractor import generate_follow_up_email

    data = request.get_json(force=True) or {}
    draft = generate_follow_up_email(
        title=data.get("title") or "Meeting",
        summary=data.get("summary") or "",
        action_items=data.get("action_items") or "",
        key_decisions=data.get("key_decisions") or "",
        open_questions=data.get("open_questions") or "",
    )
    return jsonify({"email": draft})


@app.route("/export/pdf", methods=["POST"])
@login_required
def export_pdf():
    from utils.pdf_export import build_meeting_pdf

    data = request.get_json(force=True) or {}
    include = {
        "title": bool(data.get("include_title", True)),
        "summary": bool(data.get("include_summary", True)),
        "action_items": bool(data.get("include_actions", True)),
        "key_decisions": bool(data.get("include_decisions", True)),
        "open_questions": bool(data.get("include_questions", True)),
        "transcript": bool(data.get("include_transcript", False)),
    }
    pdf_bytes = build_meeting_pdf(data, include=include)
    title = (data.get("title") or "meeting").replace(" ", "_")[:40]
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{title}_report.pdf",
    )


@app.route("/ask", methods=["POST"])
@login_required
def ask():
    from core.rag_engine import ask_question

    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    rag_chain = _rag_chain_store.get("default")
    if not rag_chain:
        return jsonify({
            "error": "No meeting processed yet. Paste a URL and click Analyze Meeting first."
        }), 400

    try:
        from core.metrics import log_event, track_stage

        with track_stage("rag_query", user_id=_current_user_id()):
            answer = ask_question(rag_chain, question)
        log_event("ask_query", user_id=_current_user_id())
        return jsonify({"answer": answer})
    except Exception as exc:
        app.logger.error("RAG error: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@app.before_request
def _metrics_start_timer():
    if request.path.startswith("/static/"):
        return
    g._metrics_start = time.perf_counter()


@app.after_request
def _add_response_headers(response):
    """Headers helpful for mobile browsers and API clients."""
    if not request.path.startswith("/static/"):
        start = getattr(g, "_metrics_start", None)
        if start is not None:
            from core.metrics import log_request

            duration_ms = (time.perf_counter() - start) * 1000
            log_request(
                path=request.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=_current_user_id(),
            )

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Avoid stale HTML/CSS/JS on mobile after deploys
    if request.path == "/" or request.path.startswith("/static/"):
        if request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=0, must-revalidate")
        else:
            response.headers.setdefault("Cache-Control", "no-store")
    elif request.path.startswith("/api/") or request.path in (
        "/process", "/ask", "/meetings", "/ready", "/health", "/follow-up-email", "/stats"
    ) or request.path.startswith("/meetings/") or request.path.startswith("/export/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.errorhandler(404)
def not_found(_err):
    wants_json = (
        request.path.startswith("/api/")
        or request.path.startswith("/meetings")
        or request.path in ("/process", "/ask", "/ready", "/health", "/follow-up-email")
        or request.path.startswith("/export/")
        or "application/json" in (request.headers.get("Accept") or "")
    )
    if wants_json:
        return jsonify({"error": "Not found", "path": request.path}), 404
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(413)
def too_large(_err):
    return jsonify({
        "error": "File is too large. Max upload size is 500 MB.",
    }), 413


@app.errorhandler(500)
def server_error(_err):
    return jsonify({"error": "Internal server error"}), 500

@app.route("/api/metrics", methods=["GET"])
@login_required
def api_metrics():
    """Usage and performance summary for reporting / debugging."""
    from core.metrics import get_metrics_summary

    return jsonify(get_metrics_summary())


@app.route("/stats", methods=["GET"])
@login_required
def stats():
    """Resume-friendly usage stats (transcription, pipeline, meetings)."""
    from core.metrics import get_usage_stats

    return jsonify(get_usage_stats())


@app.route("/api/status", methods=["GET"])
def api_status():
    """Lightweight health for mobile clients / PWA checks."""
    uid = _current_user_id()
    ready = _check_ready()
    return jsonify({
        "ok": True,
        "authenticated": bool(uid),
        "ready": ready.get("ready", False),
        "message": ready.get("message"),
        "mobile_friendly": True,
    })


# Ensure SQLite tables exist when Gunicorn workers import app:app
try:
    from core.meeting_store import init_db as _init_meetings_db
    from core.auth import init_users_db as _init_users_db
    from core.metrics import init_metrics_db as _init_metrics_db

    _init_meetings_db()
    _init_users_db()
    _init_metrics_db()
except Exception as _boot_exc:  # pragma: no cover
    import logging
    logging.getLogger(__name__).warning("DB bootstrap failed: %s", _boot_exc)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
    print(f"MeetMind UI -> http://127.0.0.1:{port}")
    if host in ("0.0.0.0", "::"):
        print(f"LAN / mobile -> http://<your-pc-ip>:{port}")
    print("Status:", _check_ready()["message"])
    app.run(debug=True, host=host, port=port, use_reloader=False)

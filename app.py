"""
MeetMind — Flask UI wrapper for the AI Meeting Intelligence pipeline.
Exposes every capability from pipeline.py as clean REST endpoints.
"""

import os
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, abort

# --- Import your existing pipeline ---
from dotenv import load_dotenv
from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarize import summarize, generate_title
from core.extractor import extract_action_items, extract_key_decisions, extract_questions
from core.rag_engine import build_rag_chain, ask_question

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit

# Session-scoped RAG chain (single-user dev server)
# For production, use a session store or user-keyed dict.
_rag_chain_store: dict = {}

ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg", ".flac", ".mkv", ".avi", ".mov"}


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ─────────────────────────── ROUTES ───────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    """
    Main pipeline endpoint.
    Accepts:
      - JSON: { source: "youtube_url", language: "english" }
      - FormData: file=<binary>, language=<str>
    Returns full pipeline result as JSON.
    """
    language = "english"
    source_path = None
    tmp_file = None

    try:
        # ── Determine source ──
        if request.is_json:
            data = request.get_json(force=True)
            source = data.get("source", "").strip()
            language = data.get("language", "english").strip()
            if not source:
                return jsonify({"error": "No source URL provided"}), 400
        else:
            # File upload
            language = request.form.get("language", "english").strip()
            if "file" not in request.files:
                return jsonify({"error": "No file uploaded"}), 400
            upload = request.files["file"]
            if not upload.filename or not allowed_file(upload.filename):
                return jsonify({"error": "Unsupported file type"}), 400

            suffix = Path(upload.filename).suffix.lower()
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            upload.save(tmp_file.name)
            source = tmp_file.name

        if language not in ("english", "hinglish"):
            language = "english"

        # ── Run pipeline ──
        chunks     = process_input(source)
        transcript = transcribe_all(chunks, language)
        title      = generate_title(transcript)
        summary    = summarize(transcript)
        action_items  = extract_action_items(transcript)
        key_decisions = extract_key_decisions(transcript)
        open_questions= extract_questions(transcript)
        rag_chain     = build_rag_chain(transcript)

        # Store RAG chain for /ask
        session_id = "default"  # replace with real session ID in production
        _rag_chain_store[session_id] = rag_chain

        return jsonify({
            "title":          title,
            "transcript":     transcript,
            "summary":        summary,
            "action_items":   action_items,
            "key_decisions":  key_decisions,
            "open_questions": open_questions,
            "rag_ready":      True,
        })

    except Exception as exc:
        app.logger.error("Pipeline error: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500

    finally:
        if tmp_file and os.path.exists(tmp_file.name):
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass


@app.route("/ask", methods=["POST"])
def ask():
    """
    RAG chat endpoint.
    Body: { question: "..." }
    Returns: { answer: "..." }
    """
    data = request.get_json(force=True)
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    session_id = "default"
    rag_chain = _rag_chain_store.get(session_id)
    if not rag_chain:
        return jsonify({"error": "No meeting processed yet. Run the pipeline first."}), 400

    try:
        answer = ask_question(rag_chain, question)
        return jsonify({"answer": answer})
    except Exception as exc:
        app.logger.error("RAG error: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────── DEV SERVER ───────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

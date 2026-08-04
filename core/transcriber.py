import whisper
import os
import requests
from pydub import AudioSegment

# Sarvam's sync STT-translate API rejects audio longer than 30s.
# We slice each chunk into 25s pieces (with a 5s safety margin) before sending.
SARVAM_PIECE_SECONDS = 25


WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")


SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text-translate"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")

_model = None


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def load_model():
    global _model

    if _model is None:
        print(f"Loading Whisper model: {WHISPER_MODEL} ...")
        _model = whisper.load_model(WHISPER_MODEL)
        print("Whisper model loaded.")
    return _model


def _chunk_start_offset(chunk_path: str, chunk_index: int, chunks: list) -> float:
    """Best-effort time offset based on previous chunk durations."""
    if chunk_index == 0:
        return 0.0
    offset = 0.0
    for prev in chunks[:chunk_index]:
        try:
            offset += len(AudioSegment.from_wav(prev)) / 1000.0
        except Exception:
            offset += 10 * 60  # default 10 min chunks used in audio_processor
    return offset


def transcribe_chunk_whisper(chunk_path: str, time_offset: float = 0.0) -> tuple[str, list]:
    model = load_model()
    result = model.transcribe(chunk_path, task="transcribe")
    text = (result.get("text") or "").strip()
    segments = []
    for seg in result.get("segments") or []:
        start = float(seg.get("start") or 0) + time_offset
        end = float(seg.get("end") or 0) + time_offset
        seg_text = (seg.get("text") or "").strip()
        if not seg_text:
            continue
        segments.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "timestamp": format_timestamp(start),
                "text": seg_text,
            }
        )
    return text, segments


def _send_to_sarvam(piece_path: str) -> str:
    """Send one ≤30s WAV file to Sarvam and return the English transcript."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {"model": SARVAM_MODEL, "with_diarization": "false"}
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    if not response.ok:
        print(f"\nSarvam returned {response.status_code}")
        print(f"Response body: {response.text}\n")
        response.raise_for_status()

    return response.json().get("transcript", "")


def transcribe_chunk_sarvam(chunk_path: str, time_offset: float = 0.0) -> tuple[str, list]:
    """
    Sarvam sync API only accepts ≤30s audio. We split this chunk into
    25-second pieces, send each separately, and join the transcripts.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in environment / .env")

    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = SARVAM_PIECE_SECONDS * 1000

    full_text = ""
    segments = []
    total_pieces = (len(audio) + piece_ms - 1) // piece_ms

    for i, start in enumerate(range(0, len(audio), piece_ms)):
        piece = audio[start: start + piece_ms]
        piece_path = f"{chunk_path}_sv_{i}.wav"
        piece.export(piece_path, format="wav")

        try:
            print(f"  -> Sarvam piece {i + 1}/{total_pieces} ...")
            piece_text = _send_to_sarvam(piece_path)
            full_text += piece_text + " "
            seg_start = time_offset + (start / 1000.0)
            segments.append(
                {
                    "start": round(seg_start, 2),
                    "end": round(seg_start + (len(piece) / 1000.0), 2),
                    "timestamp": format_timestamp(seg_start),
                    "text": piece_text.strip(),
                }
            )
        finally:
            if os.path.exists(piece_path):
                os.remove(piece_path)

    return full_text.strip(), segments


def transcribe_chunk(chunk_path: str, language: str = "english", time_offset: float = 0.0):
    """
    Route one chunk to Whisper or Sarvam depending on language choice.
    Returns (text, segments).
    """
    if language.lower() == "hinglish":
        return transcribe_chunk_sarvam(chunk_path, time_offset=time_offset)
    return transcribe_chunk_whisper(chunk_path, time_offset=time_offset)


def transcribe_all(chunks: list, language: str = "english") -> dict:
    """
    Transcribe all chunks.

    Returns:
        {
          "text": str,
          "segments": [{"start", "end", "timestamp", "text"}, ...],
          "word_count": int,
          "duration_seconds": float,
        }
    """
    full_parts = []
    all_segments = []

    engine = "Sarvam AI" if language.lower() == "hinglish" else "Whisper"
    print(f"Using {engine} for transcription.")

    for i, chunk in enumerate(chunks):
        print(f"Transcribing chunk {i + 1}/{len(chunks)}...")
        offset = _chunk_start_offset(chunk, i, chunks)
        text, segments = transcribe_chunk(chunk, language=language, time_offset=offset)
        if text:
            full_parts.append(text)
        all_segments.extend(segments)

    full_transcript = " ".join(full_parts).strip()
    duration = float(all_segments[-1]["end"]) if all_segments else 0.0
    word_count = len(full_transcript.split()) if full_transcript else 0

    print("Transcription complete.")
    return {
        "text": full_transcript,
        "segments": all_segments,
        "word_count": word_count,
        "duration_seconds": duration,
    }

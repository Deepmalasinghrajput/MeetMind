import os
import glob
import re

import yt_dlp
from pydub import AudioSegment

DOWNLOAD_DIR = "downloades"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# YouTube trusts different player clients differently. Try least-blocked first.
# Custom User-Agent overrides often make bot checks *worse* — leave UA alone.
_PLAYER_CLIENT_STRATEGIES = (
    ["tv", "web_safari"],
    ["android", "ios"],
    ["web_embedded", "mweb"],
    ["default"],
)


def _base_ydl_opts(output_template: str) -> dict:
    opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "socket_timeout": 30,
    }

    # Optional: Netscape cookies file (export from browser extension)
    cookie_file = (os.getenv("YOUTUBE_COOKIES_FILE") or "").strip()
    if cookie_file and os.path.isfile(cookie_file):
        opts["cookiefile"] = cookie_file

    # Optional: pull cookies from a local browser profile
    # Example: YOUTUBE_COOKIES_FROM_BROWSER=chrome
    browser = (os.getenv("YOUTUBE_COOKIES_FROM_BROWSER") or "").strip().lower()
    if browser:
        opts["cookiesfrombrowser"] = (browser,)

    return opts


def _is_retryable_youtube_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    markers = (
        "sign in",
        "not a bot",
        "bot",
        "confirm you're",
        "confirm you\u2019re",
        "age-restricted",
        "login required",
        "http error 403",
        "page needs to be reloaded",
        "requested format is not available",
        "this video is not available",
    )
    # "not available" only retry across clients; final message still raised if all fail
    return any(m in msg for m in markers)


def download_youtube_audio(url: str) -> str:
    """Download YouTube audio and return path to a WAV file."""
    output_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    last_error: BaseException | None = None

    for clients in _PLAYER_CLIENT_STRATEGIES:
        opts = _base_ydl_opts(output_template)
        opts["extractor_args"] = {"youtube": {"player_client": list(clients)}}
        print(f"YouTube download attempt with player_client={','.join(clients)} ...")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id") or "audio"
            return _resolve_downloaded_wav(video_id)
        except Exception as exc:
            last_error = exc
            if _is_retryable_youtube_error(exc):
                print(f"  blocked ({exc.__class__.__name__}), trying next client...")
                continue
            # Non-bot errors (bad URL, private video, etc.) — fail fast
            raise RuntimeError(f"YouTube download failed: {exc}") from exc

    hosted = bool(
        os.getenv("RENDER")
        or os.getenv("FORCE_HTTPS", "").lower() in ("1", "true", "yes")
    )
    if hosted:
        hint = (
            "YouTube blocked the download on this cloud server (bot check). "
            "This is normal on Render. Switch to Upload file and use a short "
            "audio/video recording instead — the rest of the app works the same."
        )
    else:
        hint = (
            "YouTube blocked the download (bot check / age restriction). "
            "Try: (1) Upload file instead, "
            "(2) set YOUTUBE_COOKIES_FROM_BROWSER=chrome in .env and restart, "
            "or (3) use another URL."
        )
    raise RuntimeError(hint) from last_error


def _resolve_downloaded_wav(video_id: str) -> str:
    wav_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.wav")
    if os.path.exists(wav_path):
        return wav_path

    for path in glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.*")):
        if path.lower().endswith((".wav", ".m4a", ".webm", ".mp3", ".opus")):
            if path.lower().endswith(".wav"):
                return path
            return convert_to_wav(path)

    raise FileNotFoundError(
        f"Could not find downloaded audio for video id {video_id}. "
        "Check that FFmpeg is installed and on PATH."
    )


def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to mono 16 kHz WAV."""
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    try:
        audio = AudioSegment.from_file(input_path)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read media file '{os.path.basename(input_path)}'. "
            "Install FFmpeg and use a supported audio/video format."
        ) from exc
    audio = audio.set_channels(1).set_frame_rate(16000)
    audio.export(output_path, format="wav")
    return output_path


def chunk_audio(wav_path: str, chunk_minutes: int = 10) -> list:
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000
    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start: start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")
        chunks.append(chunk_path)

    return chunks


def _looks_like_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source.strip(), re.IGNORECASE))


def process_input(source: str) -> list:
    source = (source or "").strip()
    if not source:
        raise ValueError("No media source provided")

    if _looks_like_url(source):
        print("Detected YouTube URL. Downloading audio...")
        wav_path = download_youtube_audio(source)
        # Normalize sample rate for Whisper
        if not wav_path.endswith("_converted.wav"):
            try:
                wav_path = convert_to_wav(wav_path)
            except Exception:
                pass
    else:
        if not os.path.exists(source):
            raise FileNotFoundError(f"Local file not found: {source}")
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    if not chunks:
        raise RuntimeError("Audio chunking produced no chunks. File may be empty/corrupt.")
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return chunks

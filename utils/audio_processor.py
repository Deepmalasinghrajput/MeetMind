import os
import glob

import yt_dlp
from pydub import AudioSegment

DOWNLOAD_DIR = "downloades"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_youtube_audio(url: str) -> str:
    """Download YouTube audio and return path to a WAV file."""
    # Use video id — avoids broken paths from titles with special characters
    output_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    ydl_opts = {
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
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id") or "audio"

    wav_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.wav")
    if os.path.exists(wav_path):
        return wav_path

    # Fallbacks if extension mapping differs
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
    audio = AudioSegment.from_file(input_path)
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


def process_input(source: str) -> list:
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected YouTube URL. Downloading audio...")
        wav_path = download_youtube_audio(source)
        # Normalize sample rate for Whisper
        if not wav_path.endswith("_converted.wav"):
            try:
                wav_path = convert_to_wav(wav_path)
            except Exception:
                pass
    else:
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return chunks

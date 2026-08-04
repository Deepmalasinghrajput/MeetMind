# MeetMind — production Docker image for Render / any cloud host
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=5000 \
    WHISPER_MODEL=tiny \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch

WORKDIR /app

# System deps: FFmpeg for audio, build tools for native wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch (much smaller than default CUDA builds)
RUN pip install --upgrade pip \
    && pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

# Install remaining deps without re-pulling heavy torch CUDA stacks
RUN grep -vE '^(torch|torchaudio)([=<>]|$)' requirements.txt > /tmp/requirements.docker.txt \
    && pip install -r /tmp/requirements.docker.txt \
    && rm /tmp/requirements.docker.txt

COPY . /app

# Writable dirs for SQLite + model caches
RUN mkdir -p /app/data /app/.cache/huggingface /app/.cache/torch \
    && sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

# Non-root user
RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-5000}/health" || exit 1

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]

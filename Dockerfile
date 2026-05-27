FROM python:3.13-slim

# System deps: ffmpeg for audio transcoding, gcc for some pip builds
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY scripts/ ./scripts/

# Directory for temporary TTS audio files
RUN mkdir -p /tmp/sdi_audio

EXPOSE 8000

# Run schema migrations then seed problems (idempotent), then start the server.
# PORT is injected by Railway; falls back to 8000 locally.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed_problems && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.11-slim

# System deps: ffmpeg for audio transcoding, gcc for some pip builds
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/

# Directory for temporary TTS audio files
RUN mkdir -p /tmp/sdi_audio

EXPOSE 8000

# --reload watches for code changes (volumes mounted in docker-compose for dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

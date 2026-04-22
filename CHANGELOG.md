# Changelog

All notable changes to the System Design Interviewer Bot are documented here.

---

## [2026-04-22] — Initial Setup & Full Stack Integration

### Fixed
- **Dockerfile.test** — only copied `requirements-test.txt` before `pip install`, causing build failure because it references `-r requirements.txt`. Fixed by copying both files before install.
- **tests/test_recall_client.py** — `test_does_not_raise_on_200` was creating an `httpx.Response` without a `request=` argument. Newer httpx versions call `self.request` even on 2xx responses, raising `RuntimeError`. Fixed by passing `request=req`.
- **Recall.ai API region** — base URL was hardcoded to `us-east-1`. API key was provisioned for `us-west-2`. Updated `RECALL_BASE_URL` in `recall_client.py`.
- **Recall.ai API v2 migration** — old field names (`transcription_options`, `real_time_transcription`, `status_change_webhook_url`) were silently rejected by the new API. Migrated to new schema:
  - Transcription configured via `recording_config.transcript.provider.meeting_captions`
  - Real-time webhook via `recording_config.realtime_endpoints` with event `transcript.data`
  - Status webhooks still accepted via top-level `status_change_webhook_url`
- **`recording_config.transcript`** — was incorrectly set to `True` (bool). New API requires a dict. Removed the field entirely since transcription is configured separately.
- **`play_media` → `output_audio`** — `/bot/{id}/play_media` returns 404 in the new API. New endpoint is `/bot/{id}/output_audio` which accepts `{"kind": "mp3", "b64_data": "..."}` (base64-encoded audio bytes directly — no public URL required).
- **Transcription webhook payload shape** — new API wraps events: `{"event": "transcript.data", "data": {"bot": {"id": ...}, "data": {"words": [...], "participant": {"name": ...}}}}`. Updated `main.py` webhook handler to unpack the new structure.
- **Bot self-echo** — Recall.ai transcribes the bot's own TTS audio output and sends it back as `participant.name = "Unknown"`. Bot was responding to its own voice in a loop. Fixed by adding `"unknown"` and `""` to the `_is_bot_speaker` filter.
- **`WEBHOOK_BASE_URL` stale in container** — `docker compose restart` does not re-read `.env`. Must use `docker compose up -d` to recreate the container with updated env vars.
- **Missing `os` import** — removed `uuid` and `os` imports during cleanup, causing `NameError` on startup. Restored both.

### Added
- **Ollama integration** — LLM backend is now configurable via env vars. Defaults to OpenAI; can swap to any Ollama-compatible endpoint with zero code changes.
  - `LLM_BASE_URL` — e.g. `http://host.docker.internal:11434/v1`
  - `LLM_MODEL` — e.g. `qwen2.5:1.5b-instruct`, `llama3.2`
  - `LLM_VISION_MODEL` — e.g. `llava`
- **Kokoro TTS** — free local text-to-speech replacing OpenAI `tts-1`. Added `ghcr.io/remsky/kokoro-fastapi-cpu` as a Docker service. OpenAI-compatible `/v1/audio/speech` endpoint. 67 voices available.
  - `TTS_BASE_URL` — set to `http://kokoro:8880/v1` to use Kokoro
  - `TTS_VOICE` — e.g. `af_bella`, `am_michael`, `bm_george`
- **Base64 audio delivery** — audio bytes are now sent directly to Recall.ai as base64 via `output_audio`. Eliminated the need to serve audio files over ngrok.
- **Structured interviewer introduction** — bot now opens with three distinct spoken parts: greeting as "Alex", sharing a whiteboard link, and posing the design question.
- **Excalidraw collaborative whiteboard** — generates a unique `excalidraw.com/#room={id},{key}` URL per session. Link is sent as a clickable chat message and announced verbally.
- **Random question pool** — 8 FAANG-style system design questions selected randomly each session (`INTERVIEW_QUESTIONS` in `prompts.py`).
- **Human interviewer persona** — rewrote system prompt to sound like a real senior engineer named "Alex". Removed robotic phrasing, enforced plain spoken English, no markdown or bullet points in responses.

### Changed
- **`FLUSH_DELAY`** 2.5s → 5.0s — bot waits longer after the candidate stops talking before responding.
- **`MIN_RESPONSE_INTERVAL`** 4.0s → 8.0s — prevents the bot from firing back-to-back responses.
- **`max_tokens`** 120 → 60 — forces short conversational replies; prevents the LLM from generating formatted walls of text.
- **`docker-compose.yml`** — added `kokoro` service; `app` now depends on it.
- **`config.py`** — added `llm_base_url`, `llm_model`, `llm_vision_model`, `tts_base_url`, `tts_voice` settings.

### Test results
- 117 / 117 tests passing after fixes.

---

## Template for future entries

```
## [YYYY-MM-DD] — Short description

### Fixed
- **File / component** — what was broken and how it was fixed.

### Added
- **Feature name** — what was added and why.

### Changed
- **Setting / behaviour** — old value → new value and reason.

### Removed
- **Thing removed** — why it was removed.
```

# Changelog

All notable changes to the System Design Interviewer Bot are documented here.

---

## [2026-04-24] — Structured Interview Flow + Browser UI

### Added

- **4-phase interview flow** — sessions now progress through four named phases automatically, each with its own system prompt injected into the LLM context:
  - `INTRO` — 3-exchange warm-up (small talk → role/experience → technical background). The design question is not mentioned yet.
  - `CONSTRAINTS` — triggered after 3 candidate responses. Alex reveals a brief, vague one-liner problem description and explicitly invites the candidate to ask clarifying questions before designing. Full problem details (numbers, scale) are answered one fact at a time — not volunteered upfront.
  - `DESIGN` — begins after 4 minutes in constraints. Candidate drives the design; Alex probes with moderate difficulty (failure modes, data models, consistency).
  - `DEEP_DIVE` — begins after 12 minutes in design. Adversarial mode: cost pressure, security gaps, failure cascades, CAP trade-offs, multi-region concerns.

- **Phase-specific system prompts** (`PHASE_PROMPTS` dict in `prompts.py`) — each phase injects a focused instruction block into the conversation history when that phase starts. The LLM's behavior shifts naturally without any prompt engineering tricks.

- **Problem brief/full split** — each interview problem now has two representations:
  - `brief` — a vague one-liner revealed when CONSTRAINTS phase begins (e.g. *"Design a URL shortening service."*)
  - `full` — the complete problem with scale numbers, injected as a hidden system message for Alex to draw on when answering clarifying questions.

- **`_scripted_speak()`** — all hardcoded lines (greeting, phase transitions) are recorded in conversation history as assistant turns, so the LLM knows what Alex said before the candidate's first response.

- **Browser UI** (`GET /ui`) — a zero-install single-page interview app served at `http://localhost:8000/ui`:
  - **Canvas** — dot-grid background with 13 draggable component types (Client, DNS, CDN, Load Balancer, API Gateway, Service, Cache, Message Queue, SQL DB, NoSQL DB, Object Storage, Search, Worker). Drag from sidebar onto canvas. SVG cubic-bezier arrows between components; click arrow to delete. Double-click any node to rename inline. Keyboard: `Delete` removes selected node, `Esc` clears selection, `Space` triggers push-to-talk.
  - **Audio chat** — push-to-talk mic button (hold button or hold Space). Browser records via `MediaRecorder`, sends base64 WebM to the server, receives back text + base64 MP3, plays audio with a queue to prevent overlap.
  - **Phase indicator** — pill in the header changes color (indigo → amber → blue → red) as the interview progresses. A spring-animated banner announces each phase transition.
  - **Conversation transcript** — slide-in message bubbles for both Alex and the candidate. Alex's speaking waveform animates while audio plays. Problem card appears when CONSTRAINTS phase starts.
  - **Auto-reconnect** — WebSocket reconnects automatically if the connection drops.

- **`app/ui_session.py`** — WebSocket-based interview session that mirrors `InterviewSession` in `bot_runner.py` but communicates entirely via WebSocket. Audio pipeline: base64 WebM from browser → OpenAI Whisper → LLM → TTS → base64 MP3 back to browser. A dedicated `_whisper` client always targets the real OpenAI endpoint regardless of `LLM_BASE_URL` (so Ollama users can still transcribe via Whisper).

- **`WebSocket /ws/interview`** — full-duplex endpoint. Client sends `{"type": "audio", "data": "<base64>", "mime": "audio/webm"}`. Server sends `{"type": "transcript"|"response"|"phase_change"|"session_started", ...}`. Messages are dispatched as async tasks so new audio can be received while previous audio is still being processed; a lock inside `UISession` serialises LLM/TTS calls.

- **Screenshot loop deferred to DESIGN phase** — whiteboard analysis was previously started immediately on session start. It now starts when the DESIGN phase begins, since there's nothing on the whiteboard during intro or constraint clarification.

### Changed

- **`pick_question()` → `pick_problem()`** — returns a `dict` with `brief` and `full` keys instead of a plain string.
- **`_llm` → `_openai`** in `bot_runner.py` — renamed to match the mock target in the test suite (`@patch("app.bot_runner._openai")`).
- **`max_tokens`** 60 → 80 — gives the LLM a little more room for INTRO questions and deep-dive probes without losing the enforced brevity.
- **`_is_bot_speaker("")`** now returns `False` — empty speaker label is no longer treated as a bot echo. Only `"unknown"` triggers the filter. Fixes a pre-existing test failure.
- **`play_media` → `play_audio`** in the speak test — test was asserting the wrong Recall.ai method name and patching the wrong client (`_openai` instead of `_tts_client`). Fixed to match actual code path.

### Test results
- 51 / 51 tests passing.

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

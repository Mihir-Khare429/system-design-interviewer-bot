# Changelog

All notable changes to the System Design Interviewer Bot are documented here.

---

## [2026-05-14] — DPO Fine-Tuning Pipeline + Streaming Delivery + Barge-In

### Added

- **DPO training dataset** (`data/dpo_dataset.jsonl`) — 25 curated (prompt, chosen, rejected) triplets in TRL conversational format. Each `chosen` response is a concise, targeted probe (≤90 words, ends with `?`, no markdown, no answer hints). Each `rejected` response is deliberately verbose and multi-topic, encoding what Alex should *not* say. Covers URL shortener, rate limiter, news feed, chat/presence, payments, CDN, search, distributed locks, queues, sharding, leader election, multi-region, and monitoring scenarios.

- **`scripts/train_dpo.py`** — DPO LoRA fine-tuning pipeline:
  - **NF4 4-bit quantization** via bitsandbytes — fits the 8B model on 16–24 GB VRAM.
  - **LoRA adapters** via PEFT — trains only q/k/v/o/gate/up/down projections; `lora_rank=16`, `lora_alpha=32`.
  - **TRL `DPOTrainer`** — `ref_model=None` (implicit reference from pre-LoRA weights, memory-efficient), `loss_type="sigmoid"`, `optim="adamw_8bit"`.
  - **MLflow logging** — hyperparams, per-step training/eval metrics via a `TrainerCallback`, and the final LoRA adapter directory as an artifact. Experiment: `sdi-dpo`.
  - Full CLI: `--model`, `--epochs`, `--beta`, `--lr`, `--lora-rank`, `--lora-alpha`, `--batch-size`, `--grad-acc`, `--output`, `--mlflow-tracking-uri`.
  - Defaults: `meta-llama/Meta-Llama-3.2-3B-Instruct`, `DEFAULT_BETA=0.1`, `DEFAULT_LR=5e-5`, `DEFAULT_LORA_R=16`, `DEFAULT_LORA_A=32`, `EVAL_SPLIT=0.15`.

- **`scripts/eval_judge.py`** — LLM-as-judge before/after evaluation pipeline:
  - Generates responses from both base and fine-tuned models for each eval prompt via OpenAI-compatible endpoints (works with Ollama, vLLM, or real OpenAI).
  - Asks GPT-4o to score each response on four dimensions: `realism`, `challenge`, `conciseness`, `specificity` (1–5 each). Scores are parsed from JSON with a fallback to zero on parse failure.
  - Computes win rates (tuned vs base vs tie), per-dimension means, and overall means.
  - Logs all metrics and a per-prompt breakdown JSON artifact to MLflow. Can attach to an existing training run via `--run-id`.
  - CLI: `--base-url`, `--base-model`, `--tuned-url`, `--tuned-model`, `--judge-model`, `--dataset`, `--n-eval`, `--run-id`, `--mlflow-tracking-uri`, `--openai-api-key`.

- **`requirements-train.txt`** — separate requirements file for the GPU training environment: `trl>=0.9.0`, `peft>=0.10.0`, `transformers>=4.44.0`, `accelerate>=0.30.0`, `datasets>=2.18.0`, `bitsandbytes>=0.43.0`, `mlflow>=2.12.0`.

- **Streaming delivery** (`app/ui_session.py`, `app/bot_runner.py`) — LLM responses are now streamed token-by-token and split on sentence boundaries (`(?<=[.!?])\s+`). Each complete sentence is sent to TTS immediately, so the candidate hears the first sentence while the rest is still being generated. Falls back to batch mode when `LLM_STREAMING=false` (the default).

- **Barge-in handling** — if the candidate starts speaking while Alex is mid-response, streaming is interrupted between sentence boundaries:
  - **Browser UI** (`ui_session.py`) — uses `asyncio.Event` (`_barge_in`); sends `{"type": "interrupt"}` to the client to stop playback before starting the new response.
  - **Video call bot** (`bot_runner.py`) — uses a boolean flag; new transcript pushes within `MIN_RESPONSE_INTERVAL` set the flag, and the streaming loop checks it between sentences.

- **KV cache prefix tracking** (`app/context_manager.py`) — `stable_prefix_tokens()` counts the leading system messages as a cacheable prefix. Lets callers report the prefix length to the LLM provider for prompt caching efficiency.

- **`tests/test_dpo_dataset.py`** — 19 tests covering dataset schema (required keys, message structure, role validity, no duplicates) and quality (chosen ≤90 words, chosen ends with `?`, rejected wordier by sentence count, no markdown in chosen, no hint phrases, technical content in candidate turns, system prompt mentions alex/interviewer).

- **`tests/test_train_dpo.py`** — 37 tests covering `load_dataset()` (blank-line skipping, JSON error handling, large datasets, real file), `_build_parser()` (all defaults and overrides), and module constants (`DATA_PATH`, `ADAPTER_DIR`, `EVAL_SPLIT`, `DEFAULT_LR`, `DEFAULT_LORA_A = 2 × DEFAULT_LORA_R`).

- **`tests/test_eval_judge.py`** — 54 tests covering `Scores` dataclass and `mean` property, `PromptResult` defaults, `_aggregate()` (win rates, mean scores, all keys present, empty input), `_judge()` JSON parsing (well-formed JSON, embedded JSON, partial keys, float scores, invalid/empty responses, correct system prompt, candidate turn forwarded), `_print_summary()`, `_build_parser()` defaults and overrides.

- **`tests/test_ui_session.py`** — added `TestSentenceChunks` (5 tests), `TestStreamGenerate` (6 tests — per-sentence `_respond` calls, message append, barge-in abort, error fallback, None delta handling), `TestBargIn` (4 tests — interrupt frame, speaking flag reset).

- **`tests/test_context_manager.py`** — added `TestStablePrefixTokens` (6 tests — counts leading system messages, stops at first non-system, full sum when all system, zero for empty input, zero when no system messages, less than full history sum).

### Changed

- **`app/bot_runner.py`** — `asyncio.get_event_loop()` → `asyncio.get_running_loop()` in `push_transcript()` to avoid deprecation warnings in Python 3.10+.
- **`tests/test_bot_runner.py`** — three `TestPushTranscript` tests converted from `def` to `async def` to work with `get_running_loop()` (requires a running event loop).
- **`tests/conftest.py`** — `LLM_STREAMING=false` set via `os.environ.setdefault` so all existing batch-mode tests continue working without modification.

### Test results

- 357 passing, 8 skipped (live LLM tests — require Ollama).
- +278 tests added vs the previous entry (87 → 357).

---

## [2026-05-04] — Context Prioritization + Problem Picker + Scorecard

### Added

- **Context prioritization (`app/context_manager.py`)** — prevents prompt bloat during long interviews. Before each LLM call, every past exchange is scored against the current user message using cosine similarity over bag-of-words TF vectors. Only the highest-scoring messages are passed to the model; system messages and the last `RECENCY_ANCHOR` (4) turns are always kept regardless of score. The full `self._history` is never modified, so the complete transcript is still available for scorecard generation.
  - Token budget: ~1,500 tokens per LLM call, flat across the entire interview.
  - Scoring cost: <2ms pure Python — no external dependencies, no network calls.
  - At turn 30+ this actively reduces latency vs. the naive full-history approach.

- **Problem picker + difficulty selector** — setup screen shown before the interview starts. Two dropdowns let the user choose:
  - *Topic* — Random / Storage / Distributed / Real-time / Messaging / Search / ML
  - *Difficulty* — Junior / Mid-level / Senior / Staff
  - Selection filters `INTERVIEW_PROBLEMS` in `prompts.py`; difficulty also injects a calibration system prompt that shifts Alex's behavior from encouraging (Junior) to sharply adversarial (Staff).

- **`DIFFICULTY_PROMPTS`** dict in `prompts.py` — four named calibration strings (easy, medium, hard, staff) injected as a system message at session start, before the INTRO phase prompt.

- **`pick_problem(topic, difficulty)`** — replaces `pick_question()`. Filters the problem pool by `category` and `difficulty` fields; falls back gracefully to the full pool if no match.

- **Scorecard / feedback modal** — "End Interview" button sends `{"type": "end"}` over WebSocket. The server appends `SCORECARD_PROMPT` to the full conversation history and calls the LLM at `temperature=0.2, max_tokens=500`. JSON is extracted with a `re.DOTALL` regex. The modal shows:
  - Grade box (A–F, color-coded green/yellow/red)
  - Hire recommendation pill (Strong Yes / Yes / Lean No / No)
  - One-paragraph summary
  - Strengths / Gaps / Study topics sections

- **`UISession.generate_scorecard()`** — sends `scorecard_loading` first, then `scorecard` with the parsed data (or an error message on parse failure).

- **`SCORECARD_PROMPT`** in `prompts.py` — instructs the LLM to return a single JSON object with keys: `grade`, `hire`, `summary`, `strengths`, `gaps`, `study`.

- **`tests/test_context_manager.py`** — 35 offline unit tests covering:
  - `_tokenize`, `_term_freq`, `_cosine`, `_approx_tokens` helpers
  - Short-conversation passthrough (no pruning when under budget)
  - System messages always preserved and appearing first
  - Recency anchor always preserved and appearing at the end
  - Token budget respected on verbose 30-turn conversations
  - Relevant messages prioritised over irrelevant ones
  - Original message ordering preserved after scoring
  - Edge cases: empty history, empty query, single-turn, immutability of input

### Changed

- **`UISession.__init__`** — now accepts `topic: str = ""` and `difficulty: str = "medium"` and stores them for use in `start()`.
- **`UISession._generate()`** — calls `prioritize(self._history[:-1], user_text)` to build the active context before each LLM call. `self._history` is still the full transcript.
- **`create_ui_session()`** — forwards `topic` and `difficulty` to `UISession`.
- **`GET /ws/interview`** — FastAPI WebSocket handler reads `topic` and `difficulty` as query parameters.
- **`app/static/index.html`** — setup screen replaces the previous auto-connect on page load. WebSocket connection is deferred until "Begin Interview" is clicked. Header now shows topic/difficulty badges (color-coded by difficulty level). Phase transitions announce themselves with a spring-animated banner.

### Test results
- All existing tests continue to pass.
- 35 new tests added in `test_context_manager.py`.

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

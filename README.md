# System Design Interviewer Bot

An AI interviewer that conducts structured, real-feeling system design interviews. Two ways to use it:

| Mode | How |
|---|---|
| **Browser app** | Open `http://localhost:3000` — choose a problem, draw your design on a whiteboard, and talk to Alex via mic |
| **Video call bot** | Bot joins your Zoom / Google Meet, speaks via TTS, listens via transcription |

Alex is a **Senior Staff Engineer** persona that runs a 4-phase interview: warm-up → constraint clarification → design → adversarial deep dive. At the end, it generates a structured performance scorecard and updates the candidate's long-lived strengths/weaknesses profile for future practice.

---

## Interview Flow

Every session follows the same four phases, escalating naturally:

| Phase | Duration | What happens |
|---|---|---|
| **Intro** | ~3 exchanges | Small talk, then background and technical experience questions |
| **Constraints** | 4 min | Brief, vague problem given. Candidate asks clarifying questions; Alex answers one fact at a time |
| **Design** | 12 min | Candidate drives the design. Alex probes: failure modes, data models, QPS estimates |
| **Deep Dive** | Remaining | Adversarial: cost optimisation, security, CAP trade-offs, failure cascades, multi-region |

---

## What It Does

**Both modes:**
- Introduces itself as **Alex**, a Senior Staff Engineer
- Runs the full 4-phase interview flow automatically
- Speaks and responds in plain conversational English — no bullet points, no robotic phrasing
- Asks one sharp, focused question at a time
- Keeps the LLM context lean via **relevance-scored context prioritization** (see below)

**Browser app mode:**
- Next.js web app with auth, dashboard, pricing, problem selection, difficulty selection, saved interview history, and a read-only candidate profile
- React Flow whiteboard with draggable system design components (LB, Cache, DB, Queue, CDN, etc.)
- Whiteboard snapshots are sent over WebSocket, summarized, and included in Alex's prompt so follow-up questions can reference what the candidate drew
- Candidate strengths and weaknesses persist across sessions and are used to frame targeted questions in later practice interviews
- Push-to-talk mic (hold button or hold Space bar) and Live mic mode with voice activity detection
- Real-time candidate transcript draft while speaking, then server-verified transcript once Whisper returns
- Audio pipeline status bar for opening mic, recording, uploading, transcribing, thinking, speaking, scoring, and error states
- Barge-in support: when the candidate starts speaking, Alex stops talking and the stale response/audio is discarded
- **End Interview** waits for any active recording to upload/process before generating the structured scorecard

**Video call bot mode:**
- Joins Zoom / Google Meet as a participant
- Drops a shared **Excalidraw whiteboard link** in the chat
- Listens via real-time Recall.ai transcription
- Periodically analyses whiteboard screenshots and asks targeted questions
- Speaks every response via Kokoro TTS

---

## Difficulty Levels

The difficulty selector shifts Alex's entire behaviour, not just the problem complexity:

| Level | Alex's style |
|---|---|
| **Junior** | Encouraging, hints freely, broad questions |
| **Mid-level** | Balanced probing, moderate pressure |
| **Senior** | Expects trade-off justifications, digs into bottlenecks |
| **Staff** | Sharply adversarial — cost pressure, multi-region concerns, CAP theorems, failure cascades |

---

## Scorecard

After clicking **End Interview**, the bot analyses the full conversation and produces a structured report:

| Field | Description |
|---|---|
| **Grade** | A–F, colour-coded green / yellow / red |
| **Hire recommendation** | Strong Yes / Yes / Lean No / No |
| **Summary** | One-paragraph overall assessment |
| **Strengths** | What the candidate did well |
| **Gaps** | Specific weaknesses in the design |
| **Study topics** | 2–3 targeted areas to review before the next interview |

The browser app also uses the scorecard to update the candidate's accumulated profile. Repeated gaps are counted as persistent weaknesses and become higher-priority focus areas in later interviews.

---

## Candidate Memory

Candidate memory is stored at the user-account level, so it survives browser refreshes, sign-out/sign-in, and future interview sessions.

| Profile area | How it is maintained | How it is used |
|---|---|---|
| **Strengths** | Merged automatically from completed scorecards | Alex can acknowledge strong areas when relevant |
| **Weaknesses** | Merged automatically from scorecard gaps, with repeat counts | Alex explicitly targets persistent weaknesses in new subproblems |
| **Study focus** | Merged automatically from scorecard study topics | Dashboard shows what to review next |

Candidates can view their profile on the Dashboard, but they cannot edit it. Admins can correct a profile through the admin API. Set `ADMIN_EMAILS` in `.env` to auto-promote matching accounts to admin on signup/signin.

---

## Context Prioritization

Long interviews accumulate thousands of tokens of conversation history. Without management, the LLM slows down, loses focus, and starts re-asking questions the candidate already answered.

Every turn, before the LLM call:
1. Each past exchange is scored against the current user message using **cosine similarity over word-frequency vectors** — a fast in-process search over the conversation history.
2. The highest-scoring chunks are kept; lower-scoring ones are dropped for this turn only.
3. System messages and the 4 most recent turns are always kept regardless of score.

**Result:** The active context stays at ~1,500 tokens per turn no matter how long the conversation runs. The full history is preserved in memory for scorecard generation.

| Turn | Naive (full history) | With prioritization |
|---|---|---|
| 5 | ~400 tokens | ~400 tokens |
| 15 | ~2,000 tokens | ~1,500 tokens |
| 30 | ~5,000 tokens | ~1,500 tokens |
| 45 | ~8,000 tokens | ~1,500 tokens |

Scoring overhead: <2ms (pure Python, no network calls, no external dependencies).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Your Machine                          │
│                                                              │
│  ┌───────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐  │
│  │ Next.js   │   │ FastAPI  │   │ Kokoro   │   │ Ollama    │  │
│  │ frontend  │──▶│ API      │──▶│ TTS      │   │ LLM       │  │
│  │ :3000     │   │ :8000    │   │ :8880    │   │ :11434    │  │
│  └───────────┘   └────┬─────┘   └──────────┘   └───────────┘  │
│                       │ Video Call Bot                         │
│                ┌──────▼─────┐                                  │
│                │   ngrok    │ ← public HTTPS                   │
│                │   :4040    │                                  │
│                └──────┬─────┘                                  │
│                       │ webhooks                               │
└─────────────────────────────────┼────────────────────────────┘
                                  │
                     ┌────────────▼──────────┐     ┌──────────────────┐
                     │      Recall.ai        │────▶│  Zoom / Meet     │
                     │    (bot service)      │◀────│  (video call)    │
                     └───────────────────────┘     └──────────────────┘
```

**Services (all run via Docker Compose):**
| Service | Purpose |
|---|---|
| `app` | FastAPI server — REST API, WebSocket interview, webhook handler, bot orchestrator |
| `kokoro` | Free local TTS — OpenAI-compatible `/v1/audio/speech` endpoint |
| `ngrok` | Public HTTPS tunnel — needed for the video call bot mode only |

**Frontend:**
| App | Purpose |
|---|---|
| `frontend` | Next.js app at `http://localhost:3000` — auth, problem catalog, whiteboard, mic controls, transcript, scorecard |

**External:**
| Service | Purpose |
|---|---|
| OpenAI Whisper | Transcribes browser mic audio in the browser app (requires `OPENAI_API_KEY`) |
| Recall.ai | Sends a bot into the video call, streams transcription, plays audio (bot mode only) |
| Ollama (host) | Runs LLM locally — chat completions + vision for whiteboard analysis |

---

## Prerequisites

| Requirement | Needed for | Notes |
|---|---|---|
| **Docker Desktop** | Both modes | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) |
| **Node.js + npm** | Browser app | Node 20+ recommended for the Next.js frontend |
| **Ollama** | Both modes | [ollama.com](https://ollama.com) — runs on your Mac/Linux host |
| **OpenAI API key** | Browser app (Whisper) | Used only for mic transcription. Kokoro + Ollama handle TTS and LLM for free |
| **Recall.ai API key** | Video call bot only | Free developer key at [recall.ai](https://www.recall.ai) — create for **us-west-2** region |
| **ngrok account** | Video call bot only | Free authtoken at [dashboard.ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken) |

> You can run the **browser app** with just Ollama + an OpenAI key (Whisper only). The video call bot is optional.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Mihir-Khare429/system-design-interviewer-bot.git
cd system-design-interviewer-bot
```

### 2. Install Ollama and pull models

```bash
# macOS
brew install ollama

# Pull models (one-time — llama3.2 ~2 GB, llava ~4 GB)
ollama pull llama3.2      # main chat model
ollama pull llava          # vision model for whiteboard analysis

# Start Ollama (keep this running in a terminal)
ollama serve
```

> The bot works with any Ollama model. `qwen2.5:1.5b-instruct` is the fastest if you want quick responses.

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
# Required for browser app (Whisper transcription)
OPENAI_API_KEY=sk-...

# Required for video call bot mode only
RECALL_API_KEY=your_recall_api_key_here
NGROK_AUTHTOKEN=your_ngrok_authtoken_here
WEBHOOK_BASE_URL=https://YOUR_NGROK_SUBDOMAIN.ngrok-free.app

# LLM — Ollama (already configured for local use)
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.2
LLM_VISION_MODEL=llava

# TTS — Kokoro (already configured, no key needed)
TTS_BASE_URL=http://kokoro:8880/v1
TTS_VOICE=af_bella
```

### 4. Start the backend stack

```bash
docker compose up -d
```

Wait for all three services to start, then:

1. Visit `http://localhost:4040` and note your ngrok public URL (e.g. `https://abc123.ngrok-free.app`)
2. Paste it into `.env` as `WEBHOOK_BASE_URL`
3. Restart the app to pick up the new URL:

```bash
docker compose up -d   # recreates containers with updated .env
```

> **Important:** Use `docker compose up -d` (not `restart`) to reload `.env` changes.

If you are upgrading an existing local database, apply migrations after the backend dependencies are installed:

```bash
alembic upgrade head
```

### 5. Start the frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open `frontend/.env.local` and make sure the backend URL points at FastAPI:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

The app runs at `http://localhost:3000`.

### 6. Verify everything is running

```bash
curl http://localhost:8000/health
# → {"status": "ok", "active_sessions": 0}

curl http://localhost:8880/health
# → {"status": "healthy"}
```

---

## Running an Interview

### Option A — Browser app (recommended for solo practice)

```
http://localhost:3000
```

1. Sign up or sign in
2. Choose a problem from **Problems**
3. Pick a difficulty and click **Start interview**
4. Draw your architecture on the whiteboard
5. Talk by holding the mic button/Space bar, or use **Live** mode for voice activity detection
6. Watch the live transcript and audio status bar while Alex listens, thinks, and speaks
7. Click **End interview** to receive your scorecard

### Option B — Video call bot

```bash
curl -X POST http://localhost:8000/api/join-meeting \
  -H "Content-Type: application/json" \
  -d '{"meeting_url": "https://us04web.zoom.us/j/YOUR_MEETING_ID?pwd=..."}'
```

The bot will appear in the **waiting room**. Admit it from your Zoom/Meet UI.

Once admitted, it will automatically:
1. Greet you and introduce itself as Alex
2. Drop a shared Excalidraw whiteboard link in the meeting chat
3. Begin the interview with warm-up questions

### Session management

```bash
# List active sessions
curl http://localhost:8000/api/sessions

# End a session manually
curl -X DELETE http://localhost:8000/api/sessions/{bot_id}
```

### Watch live logs

```bash
docker compose logs -f app
```

---

## Configuration Reference

All settings are read from `.env`. See `.env.example` for the full list.

| Variable | Default | Description |
|---|---|---|
| `RECALL_API_KEY` | — | Recall.ai API key (required for video call bot) |
| `NGROK_AUTHTOKEN` | — | ngrok auth token for stable tunnel URLs |
| `WEBHOOK_BASE_URL` | `http://localhost:8000` | Public URL ngrok exposes — update after first run |
| `BOT_PERSONA_NAME` | `System Design Interviewer` | Display name in the video call |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API base — set to Ollama for free local inference |
| `LLM_MODEL` | `gpt-4o` | Chat model name |
| `LLM_VISION_MODEL` | `gpt-4o` | Vision model for whiteboard screenshot analysis |
| `TTS_BASE_URL` | `https://api.openai.com/v1` | TTS API base — set to Kokoro for free local TTS |
| `TTS_VOICE` | `onyx` | TTS voice name (`af_bella`, `am_michael`, `bm_george`, etc.) |
| `OPENAI_API_KEY` | — | Required for browser app mic transcription (Whisper). Also needed if `LLM_BASE_URL` / `TTS_BASE_URL` point to OpenAI |
| `LLM_STREAMING` | `false` | Set to `true` to enable sentence-chunked streaming delivery and barge-in interruption |
| `DATABASE_URL` | `sqlite+aiosqlite:///./sdi.db` | Local SQLite database by default; use `postgresql+asyncpg://...` in production |
| `JWT_SECRET` | `dev-secret-change-me-in-prod` | Required for auth tokens; replace in production |
| `ADMIN_EMAILS` | — | Comma-separated emails that are auto-promoted to admin on signup/signin; admins can edit candidate profiles |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Allowed frontend origin and default billing redirect base |

Frontend settings live in `frontend/.env.local`:

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL used for REST and WebSocket connections |

### Switching between OpenAI and local

**Local (free):**
```env
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.2
TTS_BASE_URL=http://kokoro:8880/v1
TTS_VOICE=af_bella
```

**OpenAI:**
```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
TTS_BASE_URL=https://api.openai.com/v1
TTS_VOICE=onyx
OPENAI_API_KEY=sk-...
```

---

## DPO Fine-Tuning

The `scripts/` directory contains a full DPO (Direct Preference Optimization) pipeline to fine-tune a small Llama-3 model to behave more like Alex.

### What it does

- **Dataset** (`data/dpo_dataset.jsonl`) — 25 curated (prompt, chosen, rejected) triplets. Each `chosen` response is a concise, targeted probe (≤90 words, ends with `?`). Each `rejected` response is a verbose, multi-topic answer that hints at the solution — exactly what Alex should *not* say.
- **Training** (`scripts/train_dpo.py`) — LoRA fine-tuning with TRL's `DPOTrainer`. Runs NF4 4-bit quantization so an 8B model fits on 16–24 GB VRAM. Hyperparameters, adapter artifacts, and per-step metrics are all logged to MLflow.
- **Evaluation** (`scripts/eval_judge.py`) — LLM-as-judge scoring. Generates responses from both base and fine-tuned models for a held-out eval set, then asks GPT-4o to score each on realism, challenge, conciseness, and specificity (1–5 each). Results are logged to MLflow alongside the raw per-prompt breakdown for drill-down analysis.

### Requirements

```bash
# Separate venv (heavy GPU deps — not needed to run the app)
python -m venv .venv-train
source .venv-train/bin/activate
pip install -r requirements-train.txt
```

Hardware: a single NVIDIA GPU with ≥16 GB VRAM (24 GB recommended for the 8B model). For CPU-only debugging, remove `bitsandbytes` and set `load_in_4bit=False` in `train_dpo.py`.

### Train

```bash
python scripts/train_dpo.py \
  --model meta-llama/Meta-Llama-3.2-3B-Instruct \
  --epochs 3 \
  --output models/lora_adapter
```

Key flags: `--beta` (DPO temperature, default 0.1), `--lora-rank` (default 16), `--lr` (default 5e-5), `--mlflow-tracking-uri`.

### Evaluate (before/after)

```bash
# Compare base Llama vs fine-tuned adapter (both served via Ollama)
python scripts/eval_judge.py \
  --base-url http://localhost:11434/v1 \
  --base-model llama3.2:3b-instruct   \
  --tuned-model sdi-interviewer        \
  --openai-api-key $OPENAI_API_KEY

# Attach eval results to the training MLflow run
python scripts/eval_judge.py --run-id <run_id_from_train>
```

### MLflow dashboard

```bash
mlflow ui --backend-store-uri ./mlruns
# → http://localhost:5000
```

---

## Streaming Delivery & Barge-In

Both the browser app and the video call bot support **sentence-chunked streaming** for lower first-token latency:

- LLM tokens are streamed and buffered until a sentence boundary (`.`, `!`, `?`) is detected.
- Each complete sentence is sent to TTS and played back immediately — the candidate hears the first sentence while the rest is still being generated.
- **Barge-in**: if the candidate starts speaking while Alex is still talking, the current TTS stream is interrupted between sentences. In the browser app a `{"type": "interrupt"}` frame is sent; in the bot runner the next response replaces the current one.

Enable streaming: set `LLM_STREAMING=true` in `.env` (default is `false` for compatibility).

---

## Browser Audio Pipeline

The browser app sends every candidate turn through an observable WebSocket pipeline:

1. Browser records WebM audio with `MediaRecorder`
2. Client sends `speech_start` immediately so Alex can stop current playback
3. Client sends `audio` with base64 data and MIME type
4. Backend replies with `audio_received`
5. Backend emits `processing_state=transcribing`, runs Whisper, then sends `transcript`
6. Backend emits `processing_state=thinking`, generates Alex's next response, queues TTS, and sends response text/audio
7. Client shows a compact status bar for recording, upload, transcription, thinking, speaking, scoring, and errors

When **End interview** is clicked during an active recording, the client waits for that final audio upload before sending `end`. The backend also serializes scorecard generation behind the active STT/LLM turn, so the final answer is included in the report.

---

## Running Tests

### Full suite (mocked — no API keys needed)

```bash
make test
```

Or in watch mode (reruns on file change):

```bash
make test-watch
```

The suite is mostly mocked and does not require API keys. Recent focused verification:

- `python -m pytest tests/test_main.py tests/test_ui_session.py -q` → 127 passed
- `python -m pytest tests/e2e/test_full_interview.py -q --timeout=120` → 1 passed and writes HTML/JSON reports under `reports/`
- `cd frontend && npm run build` → Next.js production build passes

### Human-likeness tests (requires Ollama running locally)

These make real LLM calls to verify Alex sounds like a human engineer, not a chatbot. Nine checks per scenario: no markdown, no robotic openers, correct length, ends with a question, no bullet lists, no meta-commentary, no enumeration, no all-caps words.

```bash
# Run as pytest with per-check detail
make test-human

# Generate a standalone formatted report (no pytest needed)
make report-human
```

Example report output:
```
Score: 83% — 45/54 checks passed

Perfect (6/6): no_robotic_opener, length_8_to_100, no_phase_meta, no_enumeration, no_all_caps
Problem areas:
  ends_with_question    ███░░░░░░░  2/6
  one_or_two_questions  █████░░░░░  3/6
  no_markdown           ████████░░  5/6
  no_bullet_list        ████████░░  5/6
```

---

## Supported Platforms

| Platform | Works |
|---|---|
| Zoom | ✅ |
| Google Meet | ✅ (admit bot from waiting room) |
| Microsoft Teams | ✅ |
| Webex | ✅ |
| Jitsi Meet | ❌ Not supported by Recall.ai |

---

## Kokoro TTS Voices

Preview all 67 voices at `http://localhost:8880/web/` once the stack is running.

Recommended voices:
| Voice | Style |
|---|---|
| `af_bella` | American female, warm |
| `am_michael` | American male, neutral |
| `bm_george` | British male, authoritative |
| `af_sarah` | American female, professional |

Change voice by setting `TTS_VOICE` in `.env` and running `docker compose up -d`.

---

## Project Structure

```
.
├── app/
│   ├── main.py              # FastAPI routes — webhooks, /ui, /ws/interview
│   ├── bot_runner.py        # Video call bot session — 4-phase flow, streaming, barge-in
│   ├── ui_session.py        # Browser app session — same 4-phase flow, WebSocket delivery
│   ├── context_manager.py   # Context prioritization — cosine scoring, token budget, KV prefix
│   ├── candidate_profile.py # Candidate memory — scorecard merge, profile serialization, prompt context
│   ├── recall_client.py     # Recall.ai API client
│   ├── config.py            # Settings loaded from .env
│   ├── prompts.py           # Persona, PHASE_PROMPTS, DIFFICULTY_PROMPTS, INTERVIEW_PROBLEMS
│   └── static/
│       └── index.html       # Legacy browser UI served by FastAPI
├── frontend/
│   ├── src/app/             # Next.js App Router pages
│   ├── src/components/      # Interview, whiteboard, billing, layout components
│   └── src/lib/             # API client, auth context, problem catalog
├── data/
│   └── dpo_dataset.jsonl    # 25 DPO training examples (prompt / chosen / rejected)
├── scripts/
│   ├── train_dpo.py         # DPO LoRA fine-tuning — NF4 quantization, MLflow logging
│   └── eval_judge.py        # LLM-as-judge before/after evaluation, MLflow logging
├── tests/
│   ├── test_context_manager.py  # 42 offline tests — context prioritization + KV prefix
│   ├── test_candidate_profile.py # Candidate profile merge, serialization, and prompt tests
│   ├── test_ui_session.py       # Browser session tests — audio states, scorecard, streaming, barge-in
│   ├── test_bot_runner.py       # Tests for video call session
│   ├── test_dpo_dataset.py      # 19 tests — dataset schema + quality checks
│   ├── test_train_dpo.py        # 37 tests — DPO training script (no GPU required)
│   ├── test_eval_judge.py       # 54 tests — eval pipeline (mocked API calls)
│   ├── test_human_likeness.py   # Live LLM tests — 9 human-likeness checks × 6 scenarios
│   ├── test_main.py
│   ├── test_prompts.py
│   ├── test_recall_client.py
│   ├── test_config.py
│   └── conftest.py
├── requirements-train.txt   # Heavy GPU deps for DPO training (separate venv)
├── docker-compose.yml
├── docker-compose.test.yml
├── Dockerfile
├── Dockerfile.test
├── Makefile
├── .env.example             # Template — copy to .env and fill in
├── CHANGELOG.md
└── README.md
```

---

## Troubleshooting

**Bot not speaking audio**
- Check logs: `docker compose logs -f app`
- Verify Kokoro is healthy: `curl http://localhost:8880/health`
- Confirm `TTS_BASE_URL=http://kokoro:8880/v1` in `.env` and container was recreated with `docker compose up -d`

**Bot responding to itself**
- Fixed in current version — "Unknown" transcription speaker (Recall.ai echoing bot's own TTS) is filtered out

**401 from Recall.ai**
- Verify your `RECALL_API_KEY` matches the region (`us-west-2.recall.ai`)

**LLM not responding**
- Ensure Ollama is running: `curl http://localhost:11434`
- Confirm the model is pulled: `ollama list`
- From inside Docker, Ollama is reachable at `host.docker.internal:11434`

**Responses feel slow mid-interview**
- Expected on weak hardware with large models — switch to `qwen2.5:1.5b-instruct` for faster responses
- Context prioritization keeps the prompt lean (~1,500 tokens), so latency stays flat throughout the session regardless of conversation length
- Enable `LLM_STREAMING=true` for lower first-audio latency, with sentence-level TTS delivery

**Webhook URL invalid**
- Must use `docker compose up -d` (not `docker compose restart`) to reload `.env`
- Confirm ngrok URL matches `WEBHOOK_BASE_URL`: `curl http://localhost:4040/api/tunnels`

**End Interview says "Not connected"**
- Reload the interview page once after frontend hot reloads
- Confirm the frontend points at the backend: `NEXT_PUBLIC_API_URL=http://localhost:8000`
- Confirm the backend is healthy: `curl http://localhost:8000/health`
- In development, stale WebSocket close events are guarded, but a tab opened before a frontend restart may still need a reload

**Next.js dev error: `Cannot find module './<chunk>.js'`**
- Stop `next dev`, remove `frontend/.next`, and start it again:
  ```bash
  cd frontend
  rm -rf .next
  npm run dev
  ```
- Avoid running `npm run build` while the dev server is serving from the same `.next` directory

**Bot stuck in waiting room**
- Zoom: admit the bot from the meeting controls
- Google Meet: click "Admit" in the participants panel
- Disable the waiting room in Zoom settings for automatic join

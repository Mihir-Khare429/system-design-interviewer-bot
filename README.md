# System Design Interviewer Bot

An AI interviewer that conducts structured, real-feeling system design interviews. Two ways to use it:

| Mode | How |
|---|---|
| **Browser UI** | Open `http://localhost:8000/ui` — draw your design on a canvas and talk to Alex via mic |
| **Video call bot** | Bot joins your Zoom / Google Meet, speaks via TTS, listens via transcription |

Alex is a **Senior Staff Engineer** persona that runs a 4-phase interview: warm-up → constraint clarification → design → adversarial deep dive. At the end, it generates a structured performance scorecard.

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

**Browser UI mode:**
- Setup screen to pick **topic** (Storage / Distributed / Real-time / Messaging / Search / ML) and **difficulty** (Junior / Mid-level / Senior / Staff) before starting
- Canvas with 13 draggable system design components (LB, Cache, DB, Queue, CDN, etc.)
- Arrows between components with click-to-delete
- Push-to-talk mic (hold button or hold Space bar)
- Live transcript with slide-in message bubbles
- Phase badge + animated transition banners
- **End Interview** button generates a structured AI scorecard

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
│  ┌───────────┐   ┌──────────┐   ┌──────────────────────┐    │
│  │  FastAPI  │   │  Kokoro  │   │   Ollama (host)      │    │
│  │  :8000   │   │  TTS     │   │   LLM :11434         │    │
│  │  /ui      │   │  :8880   │   │   qwen2.5 / llava    │    │
│  │  /ws/…   │   └──────────┘   └──────────────────────┘    │
│  └─────┬─────┘                                              │
│        │ Browser UI             │ Video Call Bot             │
│  ┌─────▼──────┐          ┌──────▼─────┐                     │
│  │  Browser   │          │   ngrok    │ ← public HTTPS       │
│  │  (canvas + │          │   :4040   │                      │
│  │   mic)     │          └──────┬─────┘                     │
│  └────────────┘                 │ webhooks                  │
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
| `app` | FastAPI server — canvas UI, WebSocket interview, webhook handler, bot orchestrator |
| `kokoro` | Free local TTS — OpenAI-compatible `/v1/audio/speech` endpoint |
| `ngrok` | Public HTTPS tunnel — needed for the video call bot mode only |

**External:**
| Service | Purpose |
|---|---|
| OpenAI Whisper | Transcribes browser mic audio in UI mode (requires `OPENAI_API_KEY`) |
| Recall.ai | Sends a bot into the video call, streams transcription, plays audio (bot mode only) |
| Ollama (host) | Runs LLM locally — chat completions + vision for whiteboard analysis |

---

## Prerequisites

| Requirement | Needed for | Notes |
|---|---|---|
| **Docker Desktop** | Both modes | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) |
| **Ollama** | Both modes | [ollama.com](https://ollama.com) — runs on your Mac/Linux host |
| **OpenAI API key** | Browser UI (Whisper) | Used only for mic transcription. Kokoro + Ollama handle TTS and LLM for free |
| **Recall.ai API key** | Video call bot only | Free developer key at [recall.ai](https://www.recall.ai) — create for **us-west-2** region |
| **ngrok account** | Video call bot only | Free authtoken at [dashboard.ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken) |

> You can run the **browser UI** with just Ollama + an OpenAI key (Whisper only). The video call bot is optional.

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
# Required for browser UI (Whisper transcription)
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

### 4. Start the stack

```bash
docker compose up
```

Wait for all three services to start, then:

1. Visit `http://localhost:4040` and note your ngrok public URL (e.g. `https://abc123.ngrok-free.app`)
2. Paste it into `.env` as `WEBHOOK_BASE_URL`
3. Restart the app to pick up the new URL:

```bash
docker compose up -d   # recreates containers with updated .env
```

> **Important:** Use `docker compose up -d` (not `restart`) to reload `.env` changes.

### 5. Verify everything is running

```bash
curl http://localhost:8000/health
# → {"status": "ok", "active_sessions": 0}

curl http://localhost:8880/health
# → {"status": "healthy"}
```

---

## Running an Interview

### Option A — Browser UI (recommended for solo practice)

```
http://localhost:8000/ui
```

1. **Setup screen** — choose a topic and difficulty, then click **Begin Interview**
2. **Draw** your design by dragging components from the sidebar onto the canvas
3. **Connect** components by clicking two nodes in sequence
4. **Talk** by holding the mic button (or holding the Space bar)
5. Alex hears you, responds with voice, and the phase indicator updates automatically
6. Click **End Interview** to receive your scorecard

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
| `OPENAI_API_KEY` | — | Required for browser UI mic transcription (Whisper). Also needed if `LLM_BASE_URL` / `TTS_BASE_URL` point to OpenAI |
| `LLM_STREAMING` | `false` | Set to `true` to enable sentence-chunked streaming delivery and barge-in interruption |

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

Both the browser UI and the video call bot support **sentence-chunked streaming** for lower first-token latency:

- LLM tokens are streamed and buffered until a sentence boundary (`.`, `!`, `?`) is detected.
- Each complete sentence is sent to TTS and played back immediately — the candidate hears the first sentence while the rest is still being generated.
- **Barge-in**: if the candidate starts speaking while Alex is still talking, the current TTS stream is interrupted between sentences. In the browser UI a `{"type": "interrupt"}` frame is sent; in the bot runner the next response replaces the current one.

Enable streaming: set `LLM_STREAMING=true` in `.env` (default is `false` for compatibility).

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

Current: **357 / 357 tests passing** (8 skipped — live LLM tests, see below).

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
│   ├── ui_session.py        # Browser UI session — same 4-phase flow, WebSocket delivery
│   ├── context_manager.py   # Context prioritization — cosine scoring, token budget, KV prefix
│   ├── recall_client.py     # Recall.ai API client
│   ├── config.py            # Settings loaded from .env
│   ├── prompts.py           # Persona, PHASE_PROMPTS, DIFFICULTY_PROMPTS, INTERVIEW_PROBLEMS
│   └── static/
│       └── index.html       # Browser UI — setup screen, canvas, audio chat, scorecard
├── data/
│   └── dpo_dataset.jsonl    # 25 DPO training examples (prompt / chosen / rejected)
├── scripts/
│   ├── train_dpo.py         # DPO LoRA fine-tuning — NF4 quantization, MLflow logging
│   └── eval_judge.py        # LLM-as-judge before/after evaluation, MLflow logging
├── tests/
│   ├── test_context_manager.py  # 42 offline tests — context prioritization + KV prefix
│   ├── test_ui_session.py       # 47 tests — streaming, barge-in, sentence chunking
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

**Webhook URL invalid**
- Must use `docker compose up -d` (not `docker compose restart`) to reload `.env`
- Confirm ngrok URL matches `WEBHOOK_BASE_URL`: `curl http://localhost:4040/api/tunnels`

**Bot stuck in waiting room**
- Zoom: admit the bot from the meeting controls
- Google Meet: click "Admit" in the participants panel
- Disable the waiting room in Zoom settings for automatic join

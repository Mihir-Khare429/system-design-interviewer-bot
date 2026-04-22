# System Design Interviewer Bot

An AI interviewer that joins your Zoom or Google Meet, conducts a live system design interview, speaks via text-to-speech, listens to your answers in real time, and challenges your architecture decisions like a senior engineer at a top tech company.

**Fully free to run locally** — uses Ollama for LLM inference and Kokoro for TTS. No OpenAI billing required.

---

## What It Does

- Joins a video call as a participant named **"System Design Interviewer"**
- Introduces itself as **Alex**, a Senior Staff Engineer
- Drops a shared **Excalidraw whiteboard link** in the meeting chat so both parties can draw
- Asks a random FAANG-level system design question
- Listens to your answer via real-time transcription
- Responds conversationally — probes your decisions, demands numbers, exposes failure modes
- Periodically analyzes whiteboard screenshots and asks targeted questions about what it sees
- Speaks every response aloud via Kokoro TTS

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Your Machine                        │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │  FastAPI  │   │  Kokoro  │   │  Ollama (host)   │    │
│  │  :8000   │   │  TTS     │   │  LLM :11434      │    │
│  │          │   │  :8880   │   │  qwen2.5 / llava │    │
│  └────┬─────┘   └──────────┘   └──────────────────┘    │
│       │                                                 │
│  ┌────▼─────┐                                           │
│  │  ngrok   │  ← public HTTPS tunnel                    │
│  │  :4040   │                                           │
│  └────┬─────┘                                           │
└───────┼─────────────────────────────────────────────────┘
        │ webhooks
┌───────▼──────────┐         ┌──────────────────┐
│   Recall.ai      │────────▶│  Zoom / Meet     │
│  (bot service)   │◀────────│  (video call)    │
└──────────────────┘         └──────────────────┘
```

**Services (all run via Docker Compose):**
| Service | Purpose |
|---|---|
| `app` | FastAPI server — webhook handler, session manager, bot orchestrator |
| `kokoro` | Free local TTS — OpenAI-compatible `/v1/audio/speech` endpoint |
| `ngrok` | Public HTTPS tunnel so Recall.ai can reach your local server |

**External:**
| Service | Purpose |
|---|---|
| Recall.ai | Sends a bot into the video call, streams transcription, plays audio |
| Ollama (host) | Runs LLM locally — chat completions + vision for whiteboard analysis |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Docker Desktop** | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) |
| **Ollama** | [ollama.com](https://ollama.com) — runs on your Mac/Linux host |
| **Recall.ai API key** | Free developer key at [recall.ai](https://www.recall.ai) — create for **us-west-2** region |
| **ngrok account** | Free authtoken at [dashboard.ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken) |

> OpenAI is **not required**. The stack runs entirely on free local services.

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
# Required
RECALL_API_KEY=your_recall_api_key_here
NGROK_AUTHTOKEN=your_ngrok_authtoken_here

# LLM — Ollama (already configured for local use)
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.2
LLM_VISION_MODEL=llava

# TTS — Kokoro (already configured, no key needed)
TTS_BASE_URL=http://kokoro:8880/v1
TTS_VOICE=af_bella

# Leave these as-is for now
OPENAI_API_KEY=not-needed
WEBHOOK_BASE_URL=https://YOUR_NGROK_SUBDOMAIN.ngrok-free.app
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

### Start a session

```bash
curl -X POST http://localhost:8000/api/join-meeting \
  -H "Content-Type: application/json" \
  -d '{"meeting_url": "https://us04web.zoom.us/j/YOUR_MEETING_ID?pwd=..."}'
```

The bot will appear in the **waiting room**. Admit it from your Zoom/Meet UI.

Once admitted, it will automatically:
1. Greet you and introduce itself as Alex
2. Drop a shared Excalidraw whiteboard link in the meeting chat
3. Ask you a random system design question

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
| `RECALL_API_KEY` | — | Recall.ai API key (required) |
| `NGROK_AUTHTOKEN` | — | ngrok auth token for stable tunnel URLs |
| `WEBHOOK_BASE_URL` | `http://localhost:8000` | Public URL ngrok exposes — update after first run |
| `BOT_PERSONA_NAME` | `System Design Interviewer` | Display name in the video call |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API base — set to Ollama for free local inference |
| `LLM_MODEL` | `gpt-4o` | Chat model name |
| `LLM_VISION_MODEL` | `gpt-4o` | Vision model for whiteboard screenshot analysis |
| `TTS_BASE_URL` | `https://api.openai.com/v1` | TTS API base — set to Kokoro for free local TTS |
| `TTS_VOICE` | `onyx` | TTS voice name (`af_bella`, `am_michael`, `bm_george`, etc.) |
| `OPENAI_API_KEY` | — | Only needed if `LLM_BASE_URL` / `TTS_BASE_URL` point to OpenAI |

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

## Running Tests

Tests are fully mocked — no API keys needed.

```bash
make test
```

Or in watch mode (reruns on file change):

```bash
make test-watch
```

Current coverage: **90%** across all modules.

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
│   ├── main.py           # FastAPI routes and webhook handlers
│   ├── bot_runner.py     # Interview session logic, LLM calls, TTS, audio delivery
│   ├── recall_client.py  # Recall.ai API client
│   ├── config.py         # Settings loaded from .env
│   └── prompts.py        # System prompt, interviewer persona, question pool
├── tests/                # Pytest test suite (117 tests)
├── docker-compose.yml    # App + Kokoro + ngrok
├── docker-compose.test.yml
├── Dockerfile
├── Dockerfile.test
├── .env.example          # Template — copy to .env and fill in
├── CHANGELOG.md          # Per-day change log
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

**Webhook URL invalid**
- Must use `docker compose up -d` (not `docker compose restart`) to reload `.env`
- Confirm ngrok URL matches `WEBHOOK_BASE_URL`: `curl http://localhost:4040/api/tunnels`

**Bot stuck in waiting room**
- Zoom: admit the bot from the meeting controls
- Google Meet: click "Admit" in the participants panel
- Disable the waiting room in Zoom settings for automatic join

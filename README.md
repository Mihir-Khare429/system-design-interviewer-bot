# System Design Interviewer Bot

An AI interviewer that conducts structured, real-feeling system design interviews. Two ways to use it:

| Mode | How |
|---|---|
| **Browser UI** | Open `http://localhost:8000/ui` — draw your design on a canvas and talk to Alex via mic |
| **Video call bot** | Bot joins your Zoom / Google Meet, speaks via TTS, listens via transcription |

Alex is a **Senior Staff Engineer** persona that runs a 4-phase interview: warm-up → constraint clarification → design → adversarial deep dive.

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

**Browser UI mode:**
- Canvas with 13 draggable system design components (LB, Cache, DB, Queue, CDN, etc.)
- Arrows between components with click-to-delete
- Push-to-talk mic (hold button or hold Space bar)
- Live transcript with slide-in message bubbles
- Phase badge + animated transition banners

**Video call bot mode:**
- Joins Zoom / Google Meet as a participant
- Drops a shared **Excalidraw whiteboard link** in the chat
- Listens via real-time Recall.ai transcription
- Periodically analyses whiteboard screenshots and asks targeted questions
- Speaks every response via Kokoro TTS

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

Open that URL after starting the stack. No setup beyond the `.env` above.

- **Draw** your design by dragging components from the left sidebar onto the canvas
- **Connect** components by clicking "Connect" in the toolbar, then clicking two nodes
- **Talk** by holding the mic button (or holding the Space bar)
- Alex hears you, responds with voice, and the phase indicator updates automatically

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
| `RECALL_API_KEY` | — | Recall.ai API key (required) |
| `NGROK_AUTHTOKEN` | — | ngrok auth token for stable tunnel URLs |
| `WEBHOOK_BASE_URL` | `http://localhost:8000` | Public URL ngrok exposes — update after first run |
| `BOT_PERSONA_NAME` | `System Design Interviewer` | Display name in the video call |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API base — set to Ollama for free local inference |
| `LLM_MODEL` | `gpt-4o` | Chat model name |
| `LLM_VISION_MODEL` | `gpt-4o` | Vision model for whiteboard screenshot analysis |
| `TTS_BASE_URL` | `https://api.openai.com/v1` | TTS API base — set to Kokoro for free local TTS |
| `TTS_VOICE` | `onyx` | TTS voice name (`af_bella`, `am_michael`, `bm_george`, etc.) |
| `OPENAI_API_KEY` | — | Required for browser UI mic transcription (Whisper). Also needed if `LLM_BASE_URL` / `TTS_BASE_URL` point to OpenAI |

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

Current: **51 / 51 tests passing**.

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
│   ├── main.py           # FastAPI routes — webhooks, /ui, /ws/interview
│   ├── bot_runner.py     # Video call bot session — 4-phase flow, Recall.ai delivery
│   ├── ui_session.py     # Browser UI session — same 4-phase flow, WebSocket delivery
│   ├── recall_client.py  # Recall.ai API client
│   ├── config.py         # Settings loaded from .env
│   ├── prompts.py        # Persona, PHASE_PROMPTS, INTERVIEW_PROBLEMS
│   └── static/
│       └── index.html    # Browser UI — canvas, audio chat, transcript
├── tests/                # Pytest test suite (51 tests)
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

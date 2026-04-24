"""
System Design Interrogator — FastAPI entrypoint.

Endpoints:
  GET  /health                      → liveness probe
  GET  /audio/{filename}            → serve TTS audio files for Recall.ai play_media
  POST /api/join-meeting            → create a Recall.ai bot and join a Google Meet
  POST /api/webhook/recall          → Recall.ai status change events
  POST /api/webhook/transcription   → Recall.ai real-time transcription events
  GET  /api/sessions                → list active interview sessions
  DELETE /api/sessions/{bot_id}     → manually end a session
"""

import asyncio
import base64
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, HttpUrl

from app import bot_runner
from app import ui_session as ui_runner
from app.recall_client import recall_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

AUDIO_DIR = Path("/tmp/sdi_audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("System Design Interrogator Bot is starting up.")
    yield
    logger.info("Shutting down. Stopping all active sessions...")
    for bot_id in list(bot_runner.active_session_ids()):
        await bot_runner.stop_session(bot_id)


app = FastAPI(
    title="System Design Interrogator Bot",
    description=(
        "An adversarial AI interviewer that joins Google Meet, "
        "watches your whiteboard, and challenges your system design in real time."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class JoinMeetingRequest(BaseModel):
    meeting_url: str
    bot_name: str = "System Design Interviewer"


class JoinMeetingResponse(BaseModel):
    status: str
    bot_id: str
    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health_check():
    return {
        "status": "ok",
        "active_sessions": len(bot_runner.active_session_ids()),
    }


@app.get("/audio/{filename}", tags=["ops"])
async def serve_audio(filename: str):
    """
    Serve generated TTS audio files so Recall.ai can fetch them via a public URL.
    The ngrok tunnel makes this endpoint reachable from the internet.
    """
    filepath = AUDIO_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(filepath, media_type="audio/mpeg")


@app.post("/api/join-meeting", response_model=JoinMeetingResponse, tags=["interview"])
async def join_meeting(request: JoinMeetingRequest):
    """
    Instruct the Recall.ai bot to join a Google Meet room and begin the interview.

    Example:
        POST /api/join-meeting
        { "meeting_url": "https://meet.google.com/xyz-abcd-efg" }
    """
    try:
        bot = await recall_client.create_bot(
            meeting_url=request.meeting_url,
            bot_name=request.bot_name,
        )
    except Exception as exc:
        logger.error("Failed to create bot: %s", exc)
        raise HTTPException(status_code=502, detail=f"Recall.ai error: {exc}")

    bot_id = bot["id"]
    return JoinMeetingResponse(
        status="joining",
        bot_id=bot_id,
        message=(
            f"Bot '{request.bot_name}' is requesting to join the meeting. "
            "Admit it from the waiting room to start the interview."
        ),
    )


@app.post("/api/webhook/recall", tags=["webhooks"])
async def recall_status_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Recall.ai bot status change events.

    Status codes we care about:
      - in_call_recording  → bot is live; start the interview session
      - call_ended / done / fatal → bot has left; clean up
    """
    payload = await request.json()
    logger.info("Recall status webhook: %s", payload)

    event_type = payload.get("event", "")
    data = payload.get("data", {})

    # The bot ID can appear in different fields depending on the event shape.
    bot_id: str = (
        data.get("bot_id")
        or data.get("id")
        or ""
    )

    if event_type == "bot.status_change" and bot_id:
        status_code: str = data.get("status", {}).get("code", "")

        if status_code == "in_call_recording":
            logger.info("Bot %s is live — starting interview session.", bot_id)
            background_tasks.add_task(bot_runner.start_session, bot_id)

        elif status_code in ("call_ended", "done", "fatal", "error"):
            logger.info("Bot %s exited (status=%s) — stopping session.", bot_id, status_code)
            background_tasks.add_task(bot_runner.stop_session, bot_id)

    return {"status": "ok"}


@app.post("/api/webhook/transcription", tags=["webhooks"])
async def transcription_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive real-time transcription events streamed by Recall.ai.

    Expected payload shape (AssemblyAI provider):
    {
      "bot_id": "...",
      "transcript": {
        "speaker": "Participant Name",
        "words": [{"text": "hello", ...}, ...],
        "is_final": true
      }
    }
    """
    payload = await request.json()
    logger.info("Transcription webhook: %s", payload)

    # Payload shape: {"event": "transcript.data", "data": {"bot": {"id": ...}, "data": {"words": [...], "participant": {"name": ...}}}}
    outer = payload.get("data", {})
    bot_id: str = outer.get("bot", {}).get("id", "")
    inner: dict = outer.get("data", {})
    words: list = inner.get("words", [])
    speaker: str = inner.get("participant", {}).get("name", "Unknown")

    if not words or not bot_id:
        return {"status": "ok"}

    text = " ".join(w.get("text", "") for w in words).strip()
    if text:
        background_tasks.add_task(
            bot_runner.handle_transcript_event, bot_id, text, speaker
        )

    return {"status": "ok"}


@app.get("/api/sessions", tags=["interview"])
async def list_sessions():
    ids = bot_runner.active_session_ids()
    return {"active_sessions": ids, "count": len(ids)}


@app.delete("/api/sessions/{bot_id}", tags=["interview"])
async def end_session(bot_id: str):
    """Manually terminate a session and instruct the bot to leave."""
    await bot_runner.stop_session(bot_id)
    try:
        await recall_client.leave_call(bot_id)
    except Exception:
        pass  # Bot may already be gone
    return {"status": "stopped", "bot_id": bot_id}


# ---------------------------------------------------------------------------
# Browser UI — single-page app served at /ui
# ---------------------------------------------------------------------------

_UI_HTML = Path(__file__).parent / "static" / "index.html"


@app.get("/ui", tags=["ui"], response_class=HTMLResponse)
async def serve_ui():
    """Serve the browser-based interview UI."""
    if not _UI_HTML.exists():
        raise HTTPException(status_code=503, detail="UI not built yet.")
    return HTMLResponse(_UI_HTML.read_text())


@app.websocket("/ws/interview")
async def interview_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for the browser UI interview session.

    Client sends:  {"type": "audio", "data": "<base64>", "mime": "audio/webm"}
    Server sends:  {"type": "transcript"|"response"|"phase_change"|"session_started", ...}
    """
    await websocket.accept()
    session_id = uuid.uuid4().hex[:8]
    session = ui_runner.create_ui_session(session_id, websocket)

    try:
        await websocket.send_json({"type": "session_started", "session_id": session_id})
        asyncio.create_task(session.start())

        while True:
            data = await websocket.receive_json()
            if data.get("type") == "audio":
                audio_bytes = base64.b64decode(data["data"])
                mime = data.get("mime", "audio/webm")
                asyncio.create_task(session.process_audio(audio_bytes, mime))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket session %s error: %s", session_id, exc)
    finally:
        await session.stop()
        ui_runner.remove_ui_session(session_id)

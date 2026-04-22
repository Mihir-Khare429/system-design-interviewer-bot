"""
InterviewSession — the brain of each active bot session.

Flow:
  1. Recall.ai bot joins the meeting (handled in main.py webhook).
  2. start_session() is called → bot says its opening line.
  3. Real-time transcription events arrive → handle_transcript_event().
  4. Every 30 s, a background task grabs a screenshot and probes the diagram.
  5. All bot speech goes out as:
       a) A chat message (always — visible in meeting chat).
       b) TTS audio served via FastAPI and played via Recall.ai play_media
          (only when WEBHOOK_BASE_URL is a public ngrok/production URL).
"""

import asyncio
import base64
import logging
import os
import time
import uuid
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.prompts import (
    SCREENSHOT_ANALYSIS_PROMPT,
    SYSTEM_DESIGN_INTERVIEWER_PROMPT,
    pick_question,
)
from app.recall_client import recall_client

logger = logging.getLogger(__name__)

# LLM client (OpenAI or Ollama-compatible)
_llm = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.llm_base_url,
)

# TTS client (OpenAI or Kokoro-compatible)
_tts_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.tts_base_url,
)

# Directory where TTS audio files are temporarily stored and served
AUDIO_DIR = "/tmp/sdi_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# InterviewSession
# ---------------------------------------------------------------------------


class InterviewSession:
    """
    Manages a single interview session for one bot / one meeting.

    Thread-safety note: all coroutines run on the same asyncio event loop,
    so no extra locking is needed.
    """

    # Seconds of silence to wait before flushing the transcript buffer
    FLUSH_DELAY = 5.0
    # Minimum seconds between bot responses (prevents rapid-fire replies)
    MIN_RESPONSE_INTERVAL = 8.0
    # How often to grab a screenshot and probe the whiteboard
    SCREENSHOT_INTERVAL = 30

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        self.is_active = True

        self._history: list[dict] = [
            {"role": "system", "content": SYSTEM_DESIGN_INTERVIEWER_PROMPT}
        ]
        self._transcript_buffer: list[str] = []
        self._flush_handle: Optional[asyncio.TimerHandle] = None
        self._last_spoke_at: float = 0.0
        self._screenshot_task: Optional[asyncio.Task] = None
        self._speaking_lock = asyncio.Lock()  # prevent overlapping TTS

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("[%s] Session starting.", self.bot_id)

        import secrets, base64 as _b64
        room_id = secrets.token_hex(10)          # 20 hex chars
        enc_key = _b64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode()
        whiteboard_url = f"https://excalidraw.com/#room={room_id},{enc_key}"
        question = pick_question()

        # Store question in history so the LLM knows the context
        self._history.append({
            "role": "system",
            "content": f"Today's question for the candidate: {question}",
        })

        # Part 1 — greeting
        await self._speak(
            "Hey, welcome. Thanks for taking the time today. "
            "I'm Alex, Senior Staff Engineer here. "
            "I'll be running your system design interview."
        )
        await asyncio.sleep(1.5)

        # Part 2 — whiteboard link (always send as chat message so it's clickable)
        await recall_client.send_chat_message(
            self.bot_id,
            f"Here's our shared whiteboard for today — feel free to draw your design there as we talk:\n{whiteboard_url}"
        )
        await self._speak(
            "I've just dropped a whiteboard link in the chat. "
            "Open it up — we'll use it to sketch out your design together."
        )
        await asyncio.sleep(2.0)

        # Part 3 — the question
        await self._speak(
            f"Alright. Here's your question: {question} "
            "Take a minute to think if you need it, then just start walking me through how you'd approach it."
        )

        self._screenshot_task = asyncio.create_task(self._screenshot_loop())

    async def stop(self) -> None:
        self.is_active = False
        if self._flush_handle:
            self._flush_handle.cancel()
        if self._screenshot_task:
            self._screenshot_task.cancel()
        logger.info("[%s] Session stopped.", self.bot_id)

    # ------------------------------------------------------------------
    # Transcript ingestion
    # ------------------------------------------------------------------

    def push_transcript(self, text: str, speaker: str) -> None:
        """
        Called from the webhook handler (synchronously) to enqueue transcript text.
        Schedules a delayed flush so we accumulate a full sentence before responding.
        """
        if not self.is_active:
            return
        # Ignore the bot's own chat messages echoed back as transcription
        if _is_bot_speaker(speaker):
            return

        logger.info("[%s] ← %s: %s", self.bot_id, speaker, text)
        self._transcript_buffer.append(text)

        # Reset the flush timer each time new words arrive
        if self._flush_handle:
            self._flush_handle.cancel()

        loop = asyncio.get_event_loop()
        self._flush_handle = loop.call_later(
            self.FLUSH_DELAY, lambda: asyncio.ensure_future(self._flush())
        )

    async def _flush(self) -> None:
        """Drain the transcript buffer and generate a response."""
        if not self._transcript_buffer or not self.is_active:
            return

        # Throttle: don't interrupt ourselves
        now = time.monotonic()
        if now - self._last_spoke_at < self.MIN_RESPONSE_INTERVAL:
            return

        combined = " ".join(self._transcript_buffer).strip()
        self._transcript_buffer.clear()

        if not combined:
            return

        response = await self._generate(combined)
        await self._speak(response)

    # ------------------------------------------------------------------
    # AI generation
    # ------------------------------------------------------------------

    async def _generate(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        try:
            completion = await _llm.chat.completions.create(
                model=settings.llm_model,
                messages=self._history,
                max_tokens=60,
                temperature=0.85,
            )
            reply = completion.choices[0].message.content.strip()
            self._history.append({"role": "assistant", "content": reply})
            logger.info("[%s] → Bot: %s", self.bot_id, reply)
            return reply
        except Exception as exc:
            logger.error("[%s] LLM error: %s", self.bot_id, exc)
            return "Could you elaborate on that point?"

    # ------------------------------------------------------------------
    # Text-to-speech + delivery
    # ------------------------------------------------------------------

    async def _speak(self, text: str) -> None:
        """
        Convert text to speech via OpenAI TTS, serve the file, and:
          - Always send as a meeting chat message (visible in all configs).
          - If WEBHOOK_BASE_URL is a public URL, also play audio via Recall.ai.
        """
        async with self._speaking_lock:
            self._last_spoke_at = time.monotonic()

            # 1. Chat message fallback (always works, even without a public URL)
            try:
                await recall_client.send_chat_message(
                    self.bot_id, f"🤖 Interviewer: {text}"
                )
            except Exception as exc:
                logger.warning("[%s] Chat message failed: %s", self.bot_id, exc)

            # 2. TTS audio sent directly as base64 — no public URL needed
            try:
                audio_bytes = await _tts(text)
                await recall_client.play_audio(self.bot_id, audio_bytes)
            except Exception as exc:
                logger.warning("[%s] TTS/play_audio failed: %s", self.bot_id, exc)

    # ------------------------------------------------------------------
    # Periodic whiteboard analysis
    # ------------------------------------------------------------------

    async def _screenshot_loop(self) -> None:
        """Every SCREENSHOT_INTERVAL seconds, analyse the bot's screen view."""
        while self.is_active:
            await asyncio.sleep(self.SCREENSHOT_INTERVAL)
            if not self.is_active:
                break
            try:
                raw = await recall_client.get_screenshot(self.bot_id)
                if raw:
                    probe = await self._analyse_screenshot(raw)
                    if probe:
                        await self._speak(probe)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[%s] Screenshot analysis skipped: %s", self.bot_id, exc)

    async def _analyse_screenshot(self, image_bytes: bytes) -> Optional[str]:
        """Send the screenshot to the vision model and get a targeted probe question."""
        try:
            b64 = base64.b64encode(image_bytes).decode()
            resp = await _llm.chat.completions.create(
                model=settings.llm_vision_model,
                messages=[
                    {"role": "system", "content": SCREENSHOT_ANALYSIS_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "This is the current state of the candidate's whiteboard. "
                                    "Identify the single most critical architectural issue and ask about it."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=80,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("[%s] Vision analysis error: %s", self.bot_id, exc)
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _tts(text: str) -> bytes:
    response = await _tts_client.audio.speech.create(
        model="kokoro" if "kokoro" in settings.tts_base_url else "tts-1",
        voice=settings.tts_voice,
        input=text,
        response_format="mp3",
    )
    return response.content


def _is_bot_speaker(speaker: str) -> bool:
    """Return True if the speaker label looks like our own bot or an echo."""
    s = speaker.strip().lower()
    # "Unknown" with no platform info = Recall.ai echoing the bot's own TTS audio
    if s in ("unknown", ""):
        return True
    bot_names = {
        "system design interviewer",
        "interviewer",
        "bot",
        settings.bot_persona_name.lower(),
    }
    return s in bot_names


# ---------------------------------------------------------------------------
# Session registry — used by main.py
# ---------------------------------------------------------------------------

_sessions: dict[str, InterviewSession] = {}


async def start_session(bot_id: str) -> None:
    if bot_id in _sessions:
        logger.warning("[%s] Session already exists — skipping duplicate start.", bot_id)
        return
    session = InterviewSession(bot_id)
    _sessions[bot_id] = session
    await session.start()


async def handle_transcript_event(bot_id: str, text: str, speaker: str) -> None:
    session = _sessions.get(bot_id)
    if session:
        session.push_transcript(text, speaker)


async def stop_session(bot_id: str) -> None:
    session = _sessions.pop(bot_id, None)
    if session:
        await session.stop()


def active_session_ids() -> list[str]:
    return list(_sessions.keys())

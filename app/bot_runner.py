"""
InterviewSession — the brain of each active bot session.

Flow:
  1. Recall.ai bot joins the meeting (handled in main.py webhook).
  2. start_session() is called → bot greets candidate and begins INTRO phase.
  3. Real-time transcription events arrive → handle_transcript_event().
  4. Session advances through 4 phases automatically:
       INTRO (3 exchanges) → CONSTRAINTS (4 min) → DESIGN (12 min) → DEEP_DIVE
  5. Screenshot probing starts when DESIGN phase begins.
  6. All bot speech goes out as:
       a) A chat message (always — visible in meeting chat).
       b) TTS audio played via Recall.ai play_audio.
"""

import asyncio
import base64
import logging
import os
import secrets
import time
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.prompts import (
    PHASE_PROMPTS,
    SCREENSHOT_ANALYSIS_PROMPT,
    SYSTEM_DESIGN_INTERVIEWER_PROMPT,
    pick_problem,
)
from app.recall_client import recall_client

logger = logging.getLogger(__name__)

# LLM client — used for chat completions and vision
_openai = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.llm_base_url,
)

# TTS client — may point to a different base URL (e.g., Kokoro for local TTS)
_tts_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.tts_base_url,
)

AUDIO_DIR = "/tmp/sdi_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Phase identifiers
_PHASE_INTRO = "INTRO"
_PHASE_CONSTRAINTS = "CONSTRAINTS"
_PHASE_DESIGN = "DESIGN"
_PHASE_DEEP_DIVE = "DEEP_DIVE"

# Phase timing
INTRO_MAX_EXCHANGES = 3       # candidate responses in INTRO before moving on
CONSTRAINTS_DURATION_S = 4 * 60   # 4 minutes in clarification
DESIGN_DURATION_S = 12 * 60       # 12 minutes of design before deep dive


# ---------------------------------------------------------------------------
# InterviewSession
# ---------------------------------------------------------------------------


class InterviewSession:
    """
    Manages a single interview session for one bot / one meeting.

    Phases:
      INTRO       — 3-exchange warm-up: small talk → background → technical depth
      CONSTRAINTS — candidate asks clarifying questions; Alex answers one fact at a time
      DESIGN      — candidate designs; Alex probes with moderate difficulty
      DEEP_DIVE   — adversarial stress-testing: cost, security, failure cascades, CAP

    Thread-safety: all coroutines run on the same asyncio event loop.
    """

    FLUSH_DELAY = 5.0            # seconds of silence before flushing transcript buffer
    MIN_RESPONSE_INTERVAL = 8.0  # minimum gap between bot responses
    SCREENSHOT_INTERVAL = 30     # seconds between whiteboard screenshot probes

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
        self._speaking_lock = asyncio.Lock()

        # Phase tracking
        self._phase: str = _PHASE_INTRO
        self._phase_start_at: float = 0.0
        self._intro_exchanges: int = 0
        self._problem: Optional[dict] = None
        self._whiteboard_url: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("[%s] Session starting.", self.bot_id)

        self._problem = pick_problem()

        room_id = secrets.token_hex(10)
        enc_key = base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode()
        self._whiteboard_url = f"https://excalidraw.com/#room={room_id},{enc_key}"

        # Inject INTRO phase instruction into history
        self._history.append({"role": "system", "content": PHASE_PROMPTS[_PHASE_INTRO]})
        self._phase_start_at = time.monotonic()

        opening = (
            "Hey — thanks for coming in today. I'm Alex, Senior Staff Engineer here, "
            "and I'll be running your system design interview. "
            "How are you doing — feeling ready for this?"
        )
        await self._scripted_speak(opening)

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
        Called from the webhook handler to enqueue transcript text.
        Schedules a delayed flush so we accumulate a full thought before responding.
        """
        if not self.is_active:
            return
        if _is_bot_speaker(speaker):
            return

        logger.info("[%s] ← %s: %s", self.bot_id, speaker, text)
        self._transcript_buffer.append(text)

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

        now = time.monotonic()
        if now - self._last_spoke_at < self.MIN_RESPONSE_INTERVAL:
            return

        combined = " ".join(self._transcript_buffer).strip()
        self._transcript_buffer.clear()

        if not combined:
            return

        # Track how many times the candidate has spoken during INTRO
        if self._phase == _PHASE_INTRO:
            self._intro_exchanges += 1

        response = await self._generate(combined)
        await self._speak(response)

        await self._check_phase_transition()

    # ------------------------------------------------------------------
    # Phase management
    # ------------------------------------------------------------------

    async def _check_phase_transition(self) -> None:
        elapsed = time.monotonic() - self._phase_start_at

        if self._phase == _PHASE_INTRO:
            if self._intro_exchanges >= INTRO_MAX_EXCHANGES:
                await self._advance_to_constraints()

        elif self._phase == _PHASE_CONSTRAINTS:
            if elapsed >= CONSTRAINTS_DURATION_S:
                await self._advance_phase(
                    _PHASE_DESIGN,
                    "Alright, I think you've got what you need. "
                    "Go ahead — walk me through your high-level design.",
                )
                if not self._screenshot_task:
                    self._screenshot_task = asyncio.create_task(self._screenshot_loop())

        elif self._phase == _PHASE_DESIGN:
            if elapsed >= DESIGN_DURATION_S:
                await self._advance_phase(
                    _PHASE_DEEP_DIVE,
                    "Okay, let's go deeper. "
                    "I want to stress-test some of the decisions you've made.",
                )

    async def _advance_to_constraints(self) -> None:
        """Transition from INTRO → CONSTRAINTS: reveal the brief problem, invite questions."""
        self._phase = _PHASE_CONSTRAINTS
        self._phase_start_at = time.monotonic()

        self._history.append({"role": "system", "content": PHASE_PROMPTS[_PHASE_CONSTRAINTS]})
        self._history.append({
            "role": "system",
            "content": (
                f"Full problem details for this session: {self._problem['full']}. "
                "Use these details when answering the candidate's clarifying questions. "
                "Do not reveal all constraints upfront — answer only what is asked."
            ),
        })

        # Drop the whiteboard link in chat so it's clickable before design begins
        await recall_client.send_chat_message(
            self.bot_id,
            f"Shared whiteboard for today — sketch your design here as we go:\n{self._whiteboard_url}",
        )

        await self._scripted_speak(
            "Alright, I think I've got a good sense of your background. "
            "Let me give you today's question."
        )
        await asyncio.sleep(1.0)
        await self._scripted_speak(
            f"{self._problem['brief']} "
            "Take a minute — ask me anything before you start designing. "
            "Scale, specific features, SLAs, whatever's on your mind."
        )

    async def _advance_phase(self, new_phase: str, transition_msg: str) -> None:
        """Transition to a new phase and inject its system prompt."""
        self._phase = new_phase
        self._phase_start_at = time.monotonic()
        self._history.append({"role": "system", "content": PHASE_PROMPTS[new_phase]})
        await self._scripted_speak(transition_msg)

    # ------------------------------------------------------------------
    # AI generation
    # ------------------------------------------------------------------

    async def _generate(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        try:
            completion = await _openai.chat.completions.create(
                model=settings.llm_model,
                messages=self._history,
                max_tokens=80,
                temperature=0.85,
            )
            reply = completion.choices[0].message.content.strip()
            self._history.append({"role": "assistant", "content": reply})
            logger.info("[%s] → Bot: %s", self.bot_id, reply)
            return reply
        except Exception as exc:
            logger.error("[%s] LLM error: %s", self.bot_id, exc)
            return "Could you elaborate on that?"

    # ------------------------------------------------------------------
    # Text-to-speech + delivery
    # ------------------------------------------------------------------

    async def _scripted_speak(self, text: str) -> None:
        """Speak a hardcoded line and record it in history so the LLM has context."""
        self._history.append({"role": "assistant", "content": text})
        await self._speak(text)

    async def _speak(self, text: str) -> None:
        """
        Deliver text via:
          1. Meeting chat message (always — visible without audio).
          2. TTS audio played via Recall.ai.
        """
        async with self._speaking_lock:
            self._last_spoke_at = time.monotonic()

            try:
                await recall_client.send_chat_message(
                    self.bot_id, f"🤖 Interviewer: {text}"
                )
            except Exception as exc:
                logger.warning("[%s] Chat message failed: %s", self.bot_id, exc)

            try:
                audio_bytes = await _tts(text)
                await recall_client.play_audio(self.bot_id, audio_bytes)
            except Exception as exc:
                logger.warning("[%s] TTS/play_audio failed: %s", self.bot_id, exc)

    # ------------------------------------------------------------------
    # Periodic whiteboard analysis (DESIGN and DEEP_DIVE phases only)
    # ------------------------------------------------------------------

    async def _screenshot_loop(self) -> None:
        """Every SCREENSHOT_INTERVAL seconds, analyse the candidate's whiteboard."""
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
            resp = await _openai.chat.completions.create(
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
    """Return True if the speaker label is the bot echoing its own TTS audio."""
    s = speaker.strip().lower()
    if s == "unknown":
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

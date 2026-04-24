"""
UISession — WebSocket-based interview session for the browser UI.

Same 4-phase logic as InterviewSession (bot_runner.py) but transport is a
WebSocket instead of Recall.ai. Audio flows: browser mic → Whisper → LLM →
TTS → base64 audio back to browser.
"""

import asyncio
import base64
import logging
import time
from typing import Optional

from fastapi import WebSocket
from openai import AsyncOpenAI

from app.config import settings
from app.prompts import (
    PHASE_PROMPTS,
    SYSTEM_DESIGN_INTERVIEWER_PROMPT,
    pick_problem,
)

logger = logging.getLogger(__name__)

_openai = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.llm_base_url,
)

# Whisper always calls the real OpenAI endpoint regardless of llm_base_url
_whisper = AsyncOpenAI(api_key=settings.openai_api_key)

_tts_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.tts_base_url,
)

_PHASE_INTRO = "INTRO"
_PHASE_CONSTRAINTS = "CONSTRAINTS"
_PHASE_DESIGN = "DESIGN"
_PHASE_DEEP_DIVE = "DEEP_DIVE"

INTRO_MAX_EXCHANGES = 3
CONSTRAINTS_DURATION_S = 4 * 60
DESIGN_DURATION_S = 12 * 60


class UISession:
    """
    Browser-facing interview session. Communicates entirely via a single WebSocket.

    Message protocol (JSON):
      Client → Server:
        {"type": "audio", "data": "<base64>", "mime": "audio/webm"}

      Server → Client:
        {"type": "session_started", "session_id": "..."}
        {"type": "transcript", "text": "..."}
        {"type": "response", "text": "...", "audio": "<base64 mp3>"}
        {"type": "phase_change", "phase": "CONSTRAINTS", "problem_brief": "..."}
        {"type": "error", "message": "..."}
    """

    def __init__(self, session_id: str, ws: WebSocket) -> None:
        self.session_id = session_id
        self.ws = ws
        self.is_active = True

        self._history: list[dict] = [
            {"role": "system", "content": SYSTEM_DESIGN_INTERVIEWER_PROMPT}
        ]
        self._phase: str = _PHASE_INTRO
        self._phase_start_at: float = 0.0
        self._intro_exchanges: int = 0
        self._problem: Optional[dict] = None
        self._lock = asyncio.Lock()  # serialise audio processing

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._problem = pick_problem()
        self._history.append({"role": "system", "content": PHASE_PROMPTS[_PHASE_INTRO]})
        self._phase_start_at = time.monotonic()

        opening = (
            "Hey — thanks for coming in today. I'm Alex, Senior Staff Engineer here, "
            "and I'll be running your system design interview. "
            "How are you doing — feeling ready for this?"
        )
        await self._scripted_respond(opening)

    async def stop(self) -> None:
        self.is_active = False

    # ------------------------------------------------------------------
    # Audio ingestion
    # ------------------------------------------------------------------

    async def process_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> None:
        if not self.is_active:
            return
        async with self._lock:
            transcript = await self._transcribe(audio_bytes, mime_type)
            if not transcript:
                return

            await self._send({"type": "transcript", "text": transcript})

            if self._phase == _PHASE_INTRO:
                self._intro_exchanges += 1

            response = await self._generate(transcript)
            await self._respond(response)
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

        elif self._phase == _PHASE_DESIGN:
            if elapsed >= DESIGN_DURATION_S:
                await self._advance_phase(
                    _PHASE_DEEP_DIVE,
                    "Okay, let's go deeper. "
                    "I want to stress-test some of the decisions you've made.",
                )

    async def _advance_to_constraints(self) -> None:
        self._phase = _PHASE_CONSTRAINTS
        self._phase_start_at = time.monotonic()

        self._history.append({"role": "system", "content": PHASE_PROMPTS[_PHASE_CONSTRAINTS]})
        self._history.append({
            "role": "system",
            "content": (
                f"Full problem details: {self._problem['full']}. "
                "Answer clarifying questions from this. "
                "Do not reveal all constraints upfront — answer only what is asked."
            ),
        })

        await self._send({
            "type": "phase_change",
            "phase": _PHASE_CONSTRAINTS,
            "problem_brief": self._problem["brief"],
        })

        await self._scripted_respond(
            "Alright, I think I've got a good sense of your background. "
            "Let me give you today's question."
        )
        await asyncio.sleep(0.5)
        await self._scripted_respond(
            f"{self._problem['brief']} "
            "Take a minute — ask me anything before you start designing. "
            "Scale, features, SLAs, whatever's on your mind."
        )

    async def _advance_phase(self, new_phase: str, transition_msg: str) -> None:
        self._phase = new_phase
        self._phase_start_at = time.monotonic()
        self._history.append({"role": "system", "content": PHASE_PROMPTS[new_phase]})
        await self._send({"type": "phase_change", "phase": new_phase})
        await self._scripted_respond(transition_msg)

    # ------------------------------------------------------------------
    # AI pipeline
    # ------------------------------------------------------------------

    async def _transcribe(self, audio_bytes: bytes, mime_type: str) -> Optional[str]:
        ext = mime_type.split("/")[-1].split(";")[0]
        try:
            result = await _whisper.audio.transcriptions.create(
                model="whisper-1",
                file=(f"audio.{ext}", audio_bytes, mime_type),
                response_format="text",
            )
            text = result.strip() if isinstance(result, str) else str(result).strip()
            logger.info("[%s] Transcript: %s", self.session_id, text)
            return text or None
        except Exception as exc:
            logger.error("[%s] Transcription error: %s", self.session_id, exc)
            return None

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
            logger.info("[%s] Response: %s", self.session_id, reply)
            return reply
        except Exception as exc:
            logger.error("[%s] LLM error: %s", self.session_id, exc)
            return "Could you elaborate on that?"

    async def _tts(self, text: str) -> Optional[bytes]:
        try:
            resp = await _tts_client.audio.speech.create(
                model="kokoro" if "kokoro" in settings.tts_base_url else "tts-1",
                voice=settings.tts_voice,
                input=text,
                response_format="mp3",
            )
            return resp.content
        except Exception as exc:
            logger.warning("[%s] TTS error: %s", self.session_id, exc)
            return None

    async def _respond(self, text: str) -> None:
        audio_bytes = await self._tts(text)
        msg: dict = {"type": "response", "text": text}
        if audio_bytes:
            msg["audio"] = base64.b64encode(audio_bytes).decode()
        await self._send(msg)

    async def _scripted_respond(self, text: str) -> None:
        self._history.append({"role": "assistant", "content": text})
        await self._respond(text)

    async def _send(self, data: dict) -> None:
        try:
            await self.ws.send_json(data)
        except Exception as exc:
            logger.warning("[%s] WS send failed: %s", self.session_id, exc)
            self.is_active = False


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

_ui_sessions: dict[str, "UISession"] = {}


def create_ui_session(session_id: str, ws: WebSocket) -> UISession:
    session = UISession(session_id, ws)
    _ui_sessions[session_id] = session
    return session


def remove_ui_session(session_id: str) -> None:
    _ui_sessions.pop(session_id, None)

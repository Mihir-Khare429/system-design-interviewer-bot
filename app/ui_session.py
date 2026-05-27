"""
UISession — WebSocket-based interview session for the browser UI.

Same 4-phase logic as InterviewSession (bot_runner.py) but transport is a
WebSocket instead of Recall.ai.

Audio pipeline (streaming path):
  browser mic → Whisper STT → LLM token stream → sentence chunker
  → TTS per sentence → base64 audio frame → browser speaker

Barge-in: when the user starts speaking while the bot is mid-utterance,
  the ongoing LLM stream is aborted between sentence boundaries and an
  {"type": "interrupt"} frame is sent so the browser can stop playback.
"""

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

from fastapi import WebSocket
from openai import AsyncOpenAI
from sqlalchemy import select

from app.config import settings
from app.context_manager import prioritize
from app.cost_tracking import CostMeter, estimate_tokens
from app.database import SessionLocal
from app.models import InterviewRun, UsageEvent
from app.prompts import (
    DIFFICULTY_PROMPTS,
    PHASE_PROMPTS,
    SCORECARD_PROMPT,
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

def _sentence_chunks(buf: str) -> tuple[list[str], str]:
    """Split *buf* on sentence boundaries; return (complete_sentences, remainder)."""
    parts = _SENTENCE_END.split(buf)
    if len(parts) <= 1:
        return [], buf
    return parts[:-1], parts[-1]


def _summarize_whiteboard(snapshot: dict[str, Any]) -> str:
    """Compress the React Flow canvas into a prompt-sized architecture summary."""
    nodes = snapshot.get("nodes") or []
    edges = snapshot.get("edges") or []
    if not nodes and not edges:
        return ""

    node_bits: list[str] = []
    label_by_id: dict[str, str] = {}
    for node in nodes[:30]:
        node_id = str(node.get("id") or "")
        label = str(node.get("label") or node.get("type") or "component").strip()
        kind = str(node.get("type") or "component").strip()
        if node_id:
            label_by_id[node_id] = label
        node_bits.append(f"{label} ({kind})")

    edge_bits: list[str] = []
    for edge in edges[:40]:
        source = str(edge.get("sourceLabel") or label_by_id.get(str(edge.get("source")), edge.get("source", ""))).strip()
        target = str(edge.get("targetLabel") or label_by_id.get(str(edge.get("target")), edge.get("target", ""))).strip()
        if source and target:
            edge_bits.append(f"{source} -> {target}")

    parts = []
    if node_bits:
        parts.append("components: " + ", ".join(node_bits))
    if edge_bits:
        parts.append("flows: " + "; ".join(edge_bits))
    return "Whiteboard architecture shows " + ". ".join(parts) + "."


_PHASE_INTRO = "INTRO"
_PHASE_CONSTRAINTS = "CONSTRAINTS"
_PHASE_DESIGN = "DESIGN"
_PHASE_DEEP_DIVE = "DEEP_DIVE"

INTRO_MAX_EXCHANGES = 3
CONSTRAINTS_DURATION_S = 4 * 60
DESIGN_DURATION_S = 12 * 60

REALTIME_CONVERSATION_PROMPT = (
    "Realtime conversation mode: keep responses concise and conversational. "
    "Ask at most one pointed follow-up at a time, avoid monologues, and let the "
    "candidate drive the design unless they are stuck. If whiteboard context is "
    "available, use it to ask specific questions about visible components, "
    "connections, missing data flows, bottlenecks, and failure paths."
)


@dataclass
class PendingSpeech:
    generation_id: int
    response_id: str
    text: str


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

    def __init__(
        self,
        session_id: str,
        ws: WebSocket,
        topic: str = "",
        difficulty: str = "medium",
        user_id: Optional[int] = None,
        problem_slug: Optional[str] = None,
    ) -> None:
        self.session_id = session_id
        self.ws = ws
        self.is_active = True
        self._topic = topic
        self._difficulty = difficulty
        self._user_id = user_id
        self._problem_slug = problem_slug

        self._history: list[dict] = [
            {"role": "system", "content": SYSTEM_DESIGN_INTERVIEWER_PROMPT}
        ]
        self._phase: str = _PHASE_INTRO
        self._phase_start_at: float = 0.0
        self._intro_exchanges: int = 0
        self._problem: Optional[dict] = None
        self._turn_lock = asyncio.Lock()  # serialise STT + LLM turn generation
        self._barge_in = asyncio.Event()
        self._speaking: bool = False
        self._generation_id: int = 0
        self._tts_queue: asyncio.Queue[Optional[PendingSpeech]] = asyncio.Queue()
        self._tts_task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()
        self._whiteboard_snapshot: Optional[dict[str, Any]] = None
        self._whiteboard_summary: str = ""
        self._meter = CostMeter()
        self._run_id: Optional[int] = None
        self._persisted_end: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._ensure_tts_worker()
        self._problem = pick_problem(topic=self._topic, difficulty=self._difficulty)
        self._history.append({"role": "system", "content": REALTIME_CONVERSATION_PROMPT})
        if self._difficulty in DIFFICULTY_PROMPTS:
            self._history.append({"role": "system", "content": DIFFICULTY_PROMPTS[self._difficulty]})
        self._history.append({"role": "system", "content": PHASE_PROMPTS[_PHASE_INTRO]})
        self._phase_start_at = time.monotonic()

        await self._create_run_record()

        opening = (
            "Hey — thanks for coming in today. I'm Alex, Senior Staff Engineer here, "
            "and I'll be running your system design interview. "
            "How are you doing — feeling ready for this?"
        )
        await self._scripted_respond(opening)

    async def stop(self) -> None:
        self.is_active = False
        await self.interrupt(notify_client=False)
        if self._tts_task:
            self._tts_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._tts_task
        await self._persist_end(status="abandoned" if not self._persisted_end else None)

    async def interrupt(self, notify_client: bool = True) -> None:
        """
        Abort any in-flight bot response. The generation id is checked by the
        LLM and TTS paths, so slow stale audio is dropped when it returns.
        """
        self._generation_id += 1
        self._barge_in.set()
        self._speaking = False
        self._clear_tts_queue()
        if notify_client and self.is_active:
            await self._send({"type": "interrupt"})

    def update_whiteboard(self, snapshot: dict[str, Any]) -> None:
        self._whiteboard_snapshot = snapshot
        self._whiteboard_summary = _summarize_whiteboard(snapshot)
        if self._whiteboard_summary:
            logger.info("[%s] Whiteboard updated: %s", self.session_id, self._whiteboard_summary)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _create_run_record(self) -> None:
        if self._user_id is None:
            return
        try:
            async with SessionLocal() as db:
                run = InterviewRun(
                    user_id=self._user_id,
                    session_id=self.session_id,
                    problem_slug=self._problem_slug or (self._problem.get("slug") if self._problem else None),
                    difficulty=self._difficulty,
                    status="active",
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)
                self._run_id = run.id
        except Exception as exc:
            logger.warning("[%s] Could not create InterviewRun: %s", self.session_id, exc)

    async def _persist_end(self, status: Optional[str] = None, scorecard: Optional[dict] = None) -> None:
        if self._user_id is None or self._run_id is None or self._persisted_end:
            return
        try:
            async with SessionLocal() as db:
                run = (await db.execute(select(InterviewRun).where(InterviewRun.id == self._run_id))).scalar_one_or_none()
                if not run:
                    return
                run.transcript_json = json.dumps([m for m in self._history if m.get("role") in ("user", "assistant")])
                if scorecard is not None:
                    run.scorecard_json = json.dumps(scorecard)
                    run.status = "completed"
                elif status:
                    run.status = status
                run.input_tokens = self._meter.input_tokens
                run.output_tokens = self._meter.output_tokens
                run.tts_chars = self._meter.tts_chars
                run.whisper_seconds = self._meter.whisper_seconds
                run.estimated_cost_usd = self._meter.total_cost_usd
                run.ended_at = datetime.now(timezone.utc)

                for ev in self._meter.events:
                    db.add(UsageEvent(
                        user_id=self._user_id,
                        interview_run_id=self._run_id,
                        kind=ev["kind"],
                        input_tokens=ev["input_tokens"],
                        output_tokens=ev["output_tokens"],
                        units=ev["units"],
                        cost_usd=ev["cost_usd"],
                    ))
                self._meter.events.clear()
                await db.commit()
            self._persisted_end = True
        except Exception as exc:
            logger.warning("[%s] Could not persist InterviewRun end: %s", self.session_id, exc)

    # ------------------------------------------------------------------
    # Score card
    # ------------------------------------------------------------------

    async def generate_scorecard(self) -> None:
        await self._send({"type": "scorecard_loading"})
        scorecard_msgs = list(self._history)
        if self._whiteboard_summary:
            scorecard_msgs.append({"role": "system", "content": self._whiteboard_prompt()})
        scorecard_msgs.append({"role": "system", "content": SCORECARD_PROMPT})
        try:
            completion = await _openai.chat.completions.create(
                model=settings.llm_model,
                messages=scorecard_msgs,
                max_tokens=500,
                temperature=0.2,
            )
            raw = completion.choices[0].message.content.strip()
            usage = getattr(completion, "usage", None)
            if usage is not None:
                self._meter.record_llm(getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group()) if m else {"summary": raw, "grade": "N/A", "hire": "N/A", "strengths": [], "gaps": [], "study": []}
        except Exception as exc:
            logger.error("[%s] Scorecard error: %s", self.session_id, exc)
            data = {"error": "Could not generate scorecard. Please review the transcript manually."}
        await self._send({"type": "scorecard", "data": data})
        await self._persist_end(scorecard=data)

    # ------------------------------------------------------------------
    # Audio ingestion
    # ------------------------------------------------------------------

    async def process_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> None:
        if not self.is_active:
            return
        await self.interrupt(notify_client=self._speaking)
        generation_id = self._generation_id

        async with self._turn_lock:
            self._barge_in.clear()
            try:
                transcript = await self._transcribe(audio_bytes, mime_type)
                if not transcript:
                    return
                if generation_id != self._generation_id or self._barge_in.is_set():
                    return

                await self._send({"type": "transcript", "text": transcript})

                if self._phase == _PHASE_INTRO:
                    self._intro_exchanges += 1

                if settings.llm_streaming:
                    await self._stream_generate(transcript, generation_id=generation_id)
                else:
                    response = await self._generate(transcript)
                    if generation_id == self._generation_id and not self._barge_in.is_set():
                        await self._queue_response(response, generation_id)
                if generation_id == self._generation_id and not self._barge_in.is_set():
                    await self._check_phase_transition()
            finally:
                if self._tts_queue.empty():
                    self._speaking = False

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

    def _active_context(self, user_text: str) -> list[dict]:
        # Trim context with relevance scoring while keeping the newest user turn
        # and the current canvas state pinned in the prompt.
        active_ctx = prioritize(self._history[:-1], user_text)
        if self._whiteboard_summary:
            active_ctx.append({"role": "system", "content": self._whiteboard_prompt()})
        active_ctx.append(self._history[-1])
        return active_ctx

    def _whiteboard_prompt(self) -> str:
        return (
            f"{self._whiteboard_summary} Use this as the candidate's current diagram. "
            "When useful, ask one specific question about the drawn architecture instead "
            "of a generic system-design follow-up."
        )

    def _ensure_tts_worker(self) -> None:
        if self._tts_task is None or self._tts_task.done():
            self._tts_task = asyncio.create_task(self._tts_worker())

    def _clear_tts_queue(self) -> None:
        while True:
            try:
                self._tts_queue.get_nowait()
                self._tts_queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def _queue_response(self, text: str, generation_id: Optional[int] = None) -> None:
        text = text.strip()
        if not text:
            return
        generation_id = self._generation_id if generation_id is None else generation_id
        if generation_id != self._generation_id or self._barge_in.is_set():
            return

        response_id = f"{generation_id}:{uuid.uuid4().hex[:8]}"
        await self._send({"type": "response", "text": text, "response_id": response_id})
        self._speaking = True
        self._ensure_tts_worker()
        await self._tts_queue.put(PendingSpeech(generation_id, response_id, text))

    async def _tts_worker(self) -> None:
        while self.is_active:
            item = await self._tts_queue.get()
            try:
                if item is None:
                    return
                if item.generation_id != self._generation_id or self._barge_in.is_set():
                    continue

                audio_bytes = await self._tts(item.text)
                if (
                    audio_bytes
                    and item.generation_id == self._generation_id
                    and not self._barge_in.is_set()
                ):
                    await self._send({
                        "type": "response_audio",
                        "response_id": item.response_id,
                        "audio": base64.b64encode(audio_bytes).decode(),
                    })
            finally:
                self._tts_queue.task_done()
                if self._tts_queue.empty():
                    self._speaking = False

    async def _transcribe(self, audio_bytes: bytes, mime_type: str) -> Optional[str]:
        ext = mime_type.split("/")[-1].split(";")[0]
        approx_seconds = max(0.5, len(audio_bytes) / 32000.0)  # ~32 KB/s for compressed webm
        self._meter.record_whisper(approx_seconds)
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

    async def _stream_generate(self, user_text: str, generation_id: Optional[int] = None) -> None:
        """Stream LLM tokens, deliver TTS per completed sentence, abort on barge-in."""
        generation_id = self._generation_id if generation_id is None else generation_id
        self._history.append({"role": "user", "content": user_text})
        active_ctx = self._active_context(user_text)
        full_reply = ""
        delivered_reply = ""
        buf = ""
        try:
            stream = await _openai.chat.completions.create(
                model=settings.llm_model,
                messages=active_ctx,
                max_tokens=120,
                temperature=0.8,
                stream=True,
            )
            async for chunk in stream:
                if self._barge_in.is_set():
                    logger.info("[%s] Barge-in: aborting generation.", self.session_id)
                    break
                if generation_id != self._generation_id:
                    logger.info("[%s] Stale generation discarded.", self.session_id)
                    break
                delta = chunk.choices[0].delta.content or ""
                full_reply += delta
                buf += delta
                sentences, buf = _sentence_chunks(buf)
                for sent in sentences:
                    if not self._barge_in.is_set() and generation_id == self._generation_id:
                        delivered_reply += sent + " "
                        await self._queue_response(sent, generation_id)
            if buf.strip() and not self._barge_in.is_set() and generation_id == self._generation_id:
                delivered_reply += buf.strip()
                await self._queue_response(buf.strip(), generation_id)
        except Exception as exc:
            logger.error("[%s] Streaming LLM error: %s", self.session_id, exc)
            if not self._barge_in.is_set() and generation_id == self._generation_id:
                fallback = "Could you elaborate on that?"
                delivered_reply = fallback
                await self._queue_response(fallback, generation_id)
        history_reply = delivered_reply.strip()
        if not history_reply and generation_id == self._generation_id and not self._barge_in.is_set():
            history_reply = full_reply.strip()
        if history_reply:
            self._history.append({"role": "assistant", "content": history_reply})
            logger.info("[%s] Response (streamed): %s", self.session_id, history_reply)
            input_est = estimate_tokens(" ".join(m.get("content", "") for m in active_ctx))
            output_est = estimate_tokens(history_reply)
            self._meter.record_llm(input_est, output_est)

    async def _generate(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        active_ctx = self._active_context(user_text)
        try:
            completion = await _openai.chat.completions.create(
                model=settings.llm_model,
                messages=active_ctx,
                max_tokens=120,
                temperature=0.8,
            )
            reply = completion.choices[0].message.content.strip()
            usage = getattr(completion, "usage", None)
            if usage is not None:
                self._meter.record_llm(getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
            self._history.append({"role": "assistant", "content": reply})
            logger.info("[%s] Response: %s", self.session_id, reply)
            return reply
        except Exception as exc:
            logger.error("[%s] LLM error: %s", self.session_id, exc)
            return "Could you elaborate on that?"

    async def _tts(self, text: str) -> Optional[bytes]:
        self._meter.record_tts(len(text))
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
        await self._queue_response(text, self._generation_id)

    async def _send(self, data: dict) -> None:
        try:
            async with self._send_lock:
                await self.ws.send_json(data)
        except Exception as exc:
            logger.warning("[%s] WS send failed: %s", self.session_id, exc)
            self.is_active = False


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

_ui_sessions: dict[str, "UISession"] = {}


def create_ui_session(
    session_id: str,
    ws: WebSocket,
    topic: str = "",
    difficulty: str = "medium",
    user_id: Optional[int] = None,
    problem_slug: Optional[str] = None,
) -> UISession:
    session = UISession(
        session_id, ws,
        topic=topic, difficulty=difficulty,
        user_id=user_id, problem_slug=problem_slug,
    )
    _ui_sessions[session_id] = session
    return session


def remove_ui_session(session_id: str) -> None:
    _ui_sessions.pop(session_id, None)

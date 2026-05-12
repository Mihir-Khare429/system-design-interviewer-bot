"""
Tests for app/ui_session.py — browser WebSocket interview session.

All OpenAI / WebSocket calls are mocked; no network traffic or real I/O occurs.
"""

import asyncio
import base64
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.ui_session import (
    UISession,
    create_ui_session,
    remove_ui_session,
    _ui_sessions,
    INTRO_MAX_EXCHANGES,
    CONSTRAINTS_DURATION_S,
    DESIGN_DURATION_S,
    _PHASE_INTRO,
    _PHASE_CONSTRAINTS,
    _PHASE_DESIGN,
    _PHASE_DEEP_DIVE,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def session(mock_ws):
    return UISession("sess_01", mock_ws, topic="url shortener", difficulty="medium")


# ── __init__ (lines 72-85) ────────────────────────────────────────────────────

class TestUISessionInit:
    def test_session_id_stored(self, mock_ws):
        s = UISession("abc123", mock_ws)
        assert s.session_id == "abc123"

    def test_is_active_on_creation(self, mock_ws):
        s = UISession("abc123", mock_ws)
        assert s.is_active is True

    def test_phase_starts_as_intro(self, mock_ws):
        s = UISession("abc123", mock_ws)
        assert s._phase == _PHASE_INTRO

    def test_history_starts_with_system_message(self, mock_ws):
        s = UISession("abc123", mock_ws)
        assert len(s._history) == 1
        assert s._history[0]["role"] == "system"

    def test_intro_exchanges_starts_at_zero(self, mock_ws):
        s = UISession("abc123", mock_ws)
        assert s._intro_exchanges == 0

    def test_topic_and_difficulty_stored(self, mock_ws):
        s = UISession("abc123", mock_ws, topic="kafka", difficulty="hard")
        assert s._topic == "kafka"
        assert s._difficulty == "hard"

    def test_websocket_stored(self, mock_ws):
        s = UISession("abc123", mock_ws)
        assert s.ws is mock_ws


# ── stop (line 106) ───────────────────────────────────────────────────────────

class TestStop:
    async def test_stop_sets_is_active_false(self, session):
        await session.stop()
        assert session.is_active is False


# ── _send (lines 281-285) ────────────────────────────────────────────────────

class TestSend:
    async def test_send_calls_ws_send_json(self, session, mock_ws):
        await session._send({"type": "test", "value": 42})
        mock_ws.send_json.assert_called_once_with({"type": "test", "value": 42})

    async def test_send_sets_inactive_on_websocket_error(self, session, mock_ws):
        mock_ws.send_json.side_effect = Exception("WS closed")
        await session._send({"type": "test"})
        assert session.is_active is False

    async def test_send_does_not_raise_on_error(self, session, mock_ws):
        mock_ws.send_json.side_effect = RuntimeError("Connection reset")
        await session._send({"type": "test"})  # must not propagate


# ── _scripted_respond (lines 277-278) ────────────────────────────────────────

class TestScriptedRespond:
    async def test_appends_assistant_message_to_history(self, session):
        with patch.object(session, "_respond", new_callable=AsyncMock):
            await session._scripted_respond("Welcome to the interview!")
        assert any(
            m["role"] == "assistant" and m["content"] == "Welcome to the interview!"
            for m in session._history
        )

    async def test_calls_respond_with_same_text(self, session):
        with patch.object(session, "_respond", new_callable=AsyncMock) as mock_respond:
            await session._scripted_respond("Hello!")
        mock_respond.assert_called_once_with("Hello!")


# ── _tts (lines 257-267) ────────────────────────────────────────────────────

class TestTts:
    async def test_returns_audio_bytes_on_success(self, session):
        mock_resp = MagicMock()
        mock_resp.content = b"fake mp3 bytes"
        with patch("app.ui_session._tts_client") as mock_client:
            mock_client.audio.speech.create = AsyncMock(return_value=mock_resp)
            result = await session._tts("Hello interviewer!")
        assert result == b"fake mp3 bytes"

    async def test_returns_none_on_tts_error(self, session):
        with patch("app.ui_session._tts_client") as mock_client:
            mock_client.audio.speech.create = AsyncMock(side_effect=Exception("TTS down"))
            result = await session._tts("Hello!")
        assert result is None

    async def test_uses_kokoro_model_when_url_contains_kokoro(self, session):
        mock_resp = MagicMock()
        mock_resp.content = b"audio"
        with patch("app.ui_session._tts_client") as mock_client, \
             patch("app.ui_session.settings") as mock_settings:
            mock_settings.tts_base_url = "http://localhost:8880/kokoro/v1"
            mock_settings.tts_voice = "onyx"
            mock_settings.llm_model = "gpt-4o"
            mock_client.audio.speech.create = AsyncMock(return_value=mock_resp)
            await session._tts("test text")
            call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["model"] == "kokoro"

    async def test_uses_tts1_model_for_openai_url(self, session):
        mock_resp = MagicMock()
        mock_resp.content = b"audio"
        with patch("app.ui_session._tts_client") as mock_client, \
             patch("app.ui_session.settings") as mock_settings:
            mock_settings.tts_base_url = "https://api.openai.com/v1"
            mock_settings.tts_voice = "onyx"
            mock_settings.llm_model = "gpt-4o"
            mock_client.audio.speech.create = AsyncMock(return_value=mock_resp)
            await session._tts("test text")
            call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["model"] == "tts-1"


# ── _respond (lines 270-274) ─────────────────────────────────────────────────

class TestRespond:
    async def test_sends_response_with_audio_when_tts_succeeds(self, session):
        with patch.object(session, "_tts", new_callable=AsyncMock, return_value=b"mp3data"), \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            await session._respond("Great answer!")
        sent = mock_send.call_args[0][0]
        assert sent["type"] == "response"
        assert sent["text"] == "Great answer!"
        assert "audio" in sent
        assert sent["audio"] == base64.b64encode(b"mp3data").decode()

    async def test_sends_response_without_audio_when_tts_fails(self, session):
        with patch.object(session, "_tts", new_callable=AsyncMock, return_value=None), \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            await session._respond("Fallback text.")
        sent = mock_send.call_args[0][0]
        assert sent["type"] == "response"
        assert "audio" not in sent


# ── _transcribe (lines 221-233) ──────────────────────────────────────────────

class TestTranscribe:
    async def test_returns_stripped_text_on_success(self, session):
        with patch("app.ui_session._whisper") as mock_whisper:
            mock_whisper.audio.transcriptions.create = AsyncMock(
                return_value="  I would use Redis  "
            )
            result = await session._transcribe(b"audio_bytes", "audio/webm")
        assert result == "I would use Redis"

    async def test_returns_none_for_empty_transcript(self, session):
        with patch("app.ui_session._whisper") as mock_whisper:
            mock_whisper.audio.transcriptions.create = AsyncMock(return_value="   ")
            result = await session._transcribe(b"audio_bytes", "audio/webm")
        assert result is None

    async def test_returns_none_on_transcription_error(self, session):
        with patch("app.ui_session._whisper") as mock_whisper:
            mock_whisper.audio.transcriptions.create = AsyncMock(
                side_effect=Exception("Whisper unavailable")
            )
            result = await session._transcribe(b"audio_bytes", "audio/webm")
        assert result is None

    async def test_passes_correct_extension_from_mime(self, session):
        with patch("app.ui_session._whisper") as mock_whisper:
            mock_whisper.audio.transcriptions.create = AsyncMock(return_value="hello")
            await session._transcribe(b"audio_bytes", "audio/mp4")
            file_arg = mock_whisper.audio.transcriptions.create.call_args[1]["file"]
        assert file_arg[0] == "audio.mp4"

    async def test_handles_non_string_whisper_result(self, session):
        mock_result = MagicMock()
        mock_result.__str__ = lambda self: "converted text"
        with patch("app.ui_session._whisper") as mock_whisper:
            mock_whisper.audio.transcriptions.create = AsyncMock(return_value=mock_result)
            result = await session._transcribe(b"audio_bytes", "audio/webm")
        assert result == "converted text"


# ── _generate (lines 236-254) ────────────────────────────────────────────────

class TestGenerate:
    async def test_returns_stripped_llm_reply(self, session):
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "  That's a solid point.  "
        with patch("app.ui_session._openai") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            result = await session._generate("I'd use consistent hashing.")
        assert result == "That's a solid point."

    async def test_appends_user_message_to_history(self, session):
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "Good."
        with patch("app.ui_session._openai") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            await session._generate("My design uses Redis.")
        user_msgs = [m for m in session._history if m["role"] == "user"]
        assert any(m["content"] == "My design uses Redis." for m in user_msgs)

    async def test_appends_assistant_reply_to_history(self, session):
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "Good answer."
        with patch("app.ui_session._openai") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            await session._generate("My design uses Redis.")
        asst_msgs = [m for m in session._history if m["role"] == "assistant"]
        assert any(m["content"] == "Good answer." for m in asst_msgs)

    async def test_returns_fallback_on_llm_error(self, session):
        with patch("app.ui_session._openai") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))
            result = await session._generate("Hello")
        assert result == "Could you elaborate on that?"

    async def test_fallback_does_not_append_to_history(self, session):
        initial_len = len(session._history)
        with patch("app.ui_session._openai") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))
            await session._generate("Hello")
        # Only the user message is appended (not a reply on error)
        assert len(session._history) == initial_len + 1


# ── generate_scorecard (lines 113-128) ───────────────────────────────────────

class TestGenerateScorecard:
    async def test_sends_scorecard_loading_first(self, session):
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(
            {"grade": "A", "hire": "yes", "summary": "great", "strengths": [], "gaps": [], "study": []}
        )
        with patch("app.ui_session._openai") as mock_openai, \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            await session.generate_scorecard()
        first_call = mock_send.call_args_list[0][0][0]
        assert first_call["type"] == "scorecard_loading"

    async def test_sends_scorecard_with_parsed_json(self, session):
        scorecard = {"grade": "B+", "hire": "lean_yes", "summary": "solid",
                     "strengths": [], "gaps": [], "study": []}
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(scorecard)
        with patch("app.ui_session._openai") as mock_openai, \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            await session.generate_scorecard()
        last_call = mock_send.call_args_list[-1][0][0]
        assert last_call["type"] == "scorecard"
        assert last_call["data"]["grade"] == "B+"

    async def test_handles_non_json_llm_response(self, session):
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "This is a plain text scorecard."
        with patch("app.ui_session._openai") as mock_openai, \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            await session.generate_scorecard()
        last_call = mock_send.call_args_list[-1][0][0]
        assert last_call["type"] == "scorecard"
        assert last_call["data"]["summary"] == "This is a plain text scorecard."

    async def test_sends_error_scorecard_on_llm_exception(self, session):
        with patch("app.ui_session._openai") as mock_openai, \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            mock_openai.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))
            await session.generate_scorecard()
        last_call = mock_send.call_args_list[-1][0][0]
        assert last_call["type"] == "scorecard"
        assert "error" in last_call["data"]


# ── process_audio (lines 135-149) ────────────────────────────────────────────

class TestProcessAudio:
    async def test_skips_processing_when_session_inactive(self, session):
        session.is_active = False
        with patch.object(session, "_transcribe", new_callable=AsyncMock) as mock_t:
            await session.process_audio(b"audio", "audio/webm")
        mock_t.assert_not_called()

    async def test_skips_on_empty_transcript(self, session):
        with patch.object(session, "_transcribe", new_callable=AsyncMock, return_value=None), \
             patch.object(session, "_generate", new_callable=AsyncMock) as mock_gen:
            await session.process_audio(b"audio", "audio/webm")
        mock_gen.assert_not_called()

    async def test_sends_transcript_to_client(self, session, mock_ws):
        with patch.object(session, "_transcribe", new_callable=AsyncMock, return_value="I use Redis"), \
             patch.object(session, "_generate", new_callable=AsyncMock, return_value="Why?"), \
             patch.object(session, "_respond", new_callable=AsyncMock), \
             patch.object(session, "_check_phase_transition", new_callable=AsyncMock):
            await session.process_audio(b"audio", "audio/webm")
        sent = [c[0][0] for c in mock_ws.send_json.call_args_list]
        transcript = next((m for m in sent if m.get("type") == "transcript"), None)
        assert transcript is not None
        assert transcript["text"] == "I use Redis"

    async def test_increments_intro_exchange_count(self, session):
        assert session._intro_exchanges == 0
        with patch.object(session, "_transcribe", new_callable=AsyncMock, return_value="Hello"), \
             patch.object(session, "_generate", new_callable=AsyncMock, return_value="Hi"), \
             patch.object(session, "_respond", new_callable=AsyncMock), \
             patch.object(session, "_check_phase_transition", new_callable=AsyncMock):
            await session.process_audio(b"audio", "audio/webm")
        assert session._intro_exchanges == 1

    async def test_does_not_increment_intro_count_in_other_phases(self, session):
        session._phase = _PHASE_DESIGN
        with patch.object(session, "_transcribe", new_callable=AsyncMock, return_value="Hello"), \
             patch.object(session, "_generate", new_callable=AsyncMock, return_value="Hi"), \
             patch.object(session, "_respond", new_callable=AsyncMock), \
             patch.object(session, "_check_phase_transition", new_callable=AsyncMock):
            await session.process_audio(b"audio", "audio/webm")
        assert session._intro_exchanges == 0


# ── _check_phase_transition (lines 156-172) ───────────────────────────────────

class TestCheckPhaseTransition:
    async def test_intro_advances_to_constraints_after_max_exchanges(self, session):
        session._intro_exchanges = INTRO_MAX_EXCHANGES
        session._problem = {"brief": "Design URL shortener", "full": "Full problem details"}
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session, "_send", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await session._check_phase_transition()
        assert session._phase == _PHASE_CONSTRAINTS

    async def test_intro_stays_if_not_enough_exchanges(self, session):
        session._intro_exchanges = INTRO_MAX_EXCHANGES - 1
        await session._check_phase_transition()
        assert session._phase == _PHASE_INTRO

    async def test_constraints_advances_to_design_after_timeout(self, session):
        session._phase = _PHASE_CONSTRAINTS
        session._phase_start_at = time.monotonic() - CONSTRAINTS_DURATION_S - 1
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session, "_send", new_callable=AsyncMock):
            await session._check_phase_transition()
        assert session._phase == _PHASE_DESIGN

    async def test_constraints_stays_before_timeout(self, session):
        session._phase = _PHASE_CONSTRAINTS
        session._phase_start_at = time.monotonic()
        await session._check_phase_transition()
        assert session._phase == _PHASE_CONSTRAINTS

    async def test_design_advances_to_deep_dive_after_timeout(self, session):
        session._phase = _PHASE_DESIGN
        session._phase_start_at = time.monotonic() - DESIGN_DURATION_S - 1
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session, "_send", new_callable=AsyncMock):
            await session._check_phase_transition()
        assert session._phase == _PHASE_DEEP_DIVE

    async def test_design_stays_before_timeout(self, session):
        session._phase = _PHASE_DESIGN
        session._phase_start_at = time.monotonic()
        await session._check_phase_transition()
        assert session._phase == _PHASE_DESIGN


# ── _advance_to_constraints (lines 179-203) ──────────────────────────────────

class TestAdvanceToConstraints:
    @pytest.fixture
    def session_with_problem(self, session):
        session._problem = {"brief": "Design a URL shortener", "full": "Full problem details here"}
        return session

    async def test_changes_phase_to_constraints(self, session_with_problem):
        with patch.object(session_with_problem, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session_with_problem, "_send", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await session_with_problem._advance_to_constraints()
        assert session_with_problem._phase == _PHASE_CONSTRAINTS

    async def test_sends_phase_change_event(self, session_with_problem):
        with patch.object(session_with_problem, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session_with_problem, "_send", new_callable=AsyncMock) as mock_send, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await session_with_problem._advance_to_constraints()
        phase_change = next(
            c[0][0] for c in mock_send.call_args_list
            if c[0][0].get("type") == "phase_change"
        )
        assert phase_change["phase"] == _PHASE_CONSTRAINTS
        assert phase_change["problem_brief"] == "Design a URL shortener"

    async def test_appends_full_problem_to_history(self, session_with_problem):
        with patch.object(session_with_problem, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session_with_problem, "_send", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await session_with_problem._advance_to_constraints()
        system_contents = [m["content"] for m in session_with_problem._history
                           if m["role"] == "system"]
        assert any("Full problem details here" in c for c in system_contents)

    async def test_calls_scripted_respond_twice(self, session_with_problem):
        with patch.object(session_with_problem, "_scripted_respond", new_callable=AsyncMock) as mock_sr, \
             patch.object(session_with_problem, "_send", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await session_with_problem._advance_to_constraints()
        assert mock_sr.call_count == 2


# ── _advance_phase (lines 210-214) ───────────────────────────────────────────

class TestAdvancePhase:
    async def test_changes_to_new_phase(self, session):
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session, "_send", new_callable=AsyncMock):
            await session._advance_phase(_PHASE_DEEP_DIVE, "Let's stress-test your decisions.")
        assert session._phase == _PHASE_DEEP_DIVE

    async def test_sends_phase_change_event(self, session):
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session, "_send", new_callable=AsyncMock) as mock_send:
            await session._advance_phase(_PHASE_DESIGN, "Design time.")
        phase_msg = next(
            c[0][0] for c in mock_send.call_args_list
            if c[0][0].get("type") == "phase_change"
        )
        assert phase_msg["phase"] == _PHASE_DESIGN

    async def test_scripted_respond_called_with_transition_message(self, session):
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock) as mock_sr, \
             patch.object(session, "_send", new_callable=AsyncMock):
            await session._advance_phase(_PHASE_DESIGN, "Go ahead and design.")
        mock_sr.assert_called_once_with("Go ahead and design.")

    async def test_appends_phase_prompt_to_history(self, session):
        initial_system_count = sum(1 for m in session._history if m["role"] == "system")
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock), \
             patch.object(session, "_send", new_callable=AsyncMock):
            await session._advance_phase(_PHASE_DESIGN, "Go ahead.")
        new_system_count = sum(1 for m in session._history if m["role"] == "system")
        assert new_system_count == initial_system_count + 1


# ── start (lines 92-103) ────────────────────────────────────────────────────

class TestStart:
    async def test_picks_a_problem(self, session):
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock):
            await session.start()
        assert session._problem is not None

    async def test_appends_phase_prompt_to_history(self, session):
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock):
            await session.start()
        system_contents = [m["content"] for m in session._history if m["role"] == "system"]
        # Initial system message + difficulty prompt + phase prompt = at least 2
        assert len(system_contents) >= 2

    async def test_sends_opening_greeting(self, session):
        with patch.object(session, "_scripted_respond", new_callable=AsyncMock) as mock_sr:
            await session.start()
        mock_sr.assert_called_once()
        greeting = mock_sr.call_args[0][0]
        assert "Alex" in greeting

    async def test_difficulty_prompt_appended_for_known_difficulty(self, mock_ws):
        s = UISession("x", mock_ws, difficulty="hard")
        with patch.object(s, "_scripted_respond", new_callable=AsyncMock):
            await s.start()
        system_contents = [m["content"] for m in s._history if m["role"] == "system"]
        # hard is a known difficulty key — its prompt should be in history
        assert len(system_contents) >= 3


# ── Session registry (lines 296-298, 302) ────────────────────────────────────

class TestSessionRegistry:
    def test_create_ui_session_returns_ui_session_instance(self, mock_ws):
        _ui_sessions.clear()
        try:
            s = create_ui_session("reg_001", mock_ws, topic="kafka", difficulty="easy")
            assert isinstance(s, UISession)
        finally:
            _ui_sessions.clear()

    def test_create_ui_session_stores_in_registry(self, mock_ws):
        _ui_sessions.clear()
        try:
            create_ui_session("reg_002", mock_ws)
            assert "reg_002" in _ui_sessions
        finally:
            _ui_sessions.clear()

    def test_remove_ui_session_deletes_entry(self, mock_ws):
        _ui_sessions.clear()
        try:
            create_ui_session("reg_003", mock_ws)
            remove_ui_session("reg_003")
            assert "reg_003" not in _ui_sessions
        finally:
            _ui_sessions.clear()

    def test_remove_nonexistent_session_does_not_raise(self):
        remove_ui_session("does_not_exist_xyz")

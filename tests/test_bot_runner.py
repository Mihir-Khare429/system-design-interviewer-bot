"""
Tests for app/bot_runner.py — InterviewSession engine and session registry.

All OpenAI and Recall.ai calls are mocked so no real API traffic is made.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

import app.bot_runner as runner
from app.bot_runner import (
    InterviewSession,
    _is_bot_speaker,
    start_session,
    stop_session,
    handle_transcript_event,
    active_session_ids,
)


# ── _is_bot_speaker ───────────────────────────────────────────────────────────

class TestIsBotSpeaker:
    def test_exact_match_interviewer(self):
        assert _is_bot_speaker("System Design Interviewer") is True

    def test_exact_match_interviewer_lowercase(self):
        assert _is_bot_speaker("system design interviewer") is True

    def test_plain_bot(self):
        assert _is_bot_speaker("bot") is True

    def test_plain_interviewer(self):
        assert _is_bot_speaker("interviewer") is True

    def test_whitespace_is_stripped(self):
        assert _is_bot_speaker("  bot  ") is True

    def test_human_speaker_not_matched(self):
        assert _is_bot_speaker("Alice") is False

    def test_candidate_speaker_not_matched(self):
        assert _is_bot_speaker("Candidate") is False

    def test_empty_string_not_matched(self):
        assert _is_bot_speaker("") is False

    def test_partial_name_not_matched(self):
        assert _is_bot_speaker("design") is False


# ── InterviewSession — init ───────────────────────────────────────────────────

class TestInterviewSessionInit:
    def test_session_starts_active(self):
        s = InterviewSession("bot_001")
        assert s.is_active is True

    def test_history_has_system_prompt(self):
        s = InterviewSession("bot_001")
        assert s._history[0]["role"] == "system"
        assert len(s._history[0]["content"]) > 50

    def test_transcript_buffer_starts_empty(self):
        s = InterviewSession("bot_001")
        assert s._transcript_buffer == []


# ── InterviewSession — push_transcript ───────────────────────────────────────

class TestPushTranscript:
    def test_appends_text_to_buffer_for_human_speaker(self):
        s = InterviewSession("bot_002")
        s.push_transcript("Hello world", "Alice")
        assert "Hello world" in s._transcript_buffer

    def test_ignores_bot_speaker(self):
        s = InterviewSession("bot_002")
        s.push_transcript("I am the bot", "bot")
        assert s._transcript_buffer == []

    def test_ignores_interviewer_speaker(self):
        s = InterviewSession("bot_002")
        s.push_transcript("Some text", "System Design Interviewer")
        assert s._transcript_buffer == []

    def test_inactive_session_ignores_all_input(self):
        s = InterviewSession("bot_002")
        s.is_active = False
        s.push_transcript("Hello", "Alice")
        assert s._transcript_buffer == []

    def test_multiple_pushes_accumulate(self):
        s = InterviewSession("bot_002")
        s.push_transcript("First", "Alice")
        s.push_transcript("Second", "Alice")
        assert len(s._transcript_buffer) == 2

    def test_cancels_existing_flush_handle(self):
        s = InterviewSession("bot_002")
        mock_handle = MagicMock()
        s._flush_handle = mock_handle
        s.push_transcript("New text", "Alice")
        mock_handle.cancel.assert_called_once()


# ── InterviewSession — _generate ─────────────────────────────────────────────

class TestGenerate:
    @patch("app.bot_runner._openai")
    async def test_returns_model_response(self, mock_openai):
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="What's your SLA?"))]
            )
        )
        s = InterviewSession("bot_003")
        result = await s._generate("I'd use a single server.")
        assert result == "What's your SLA?"

    @patch("app.bot_runner._openai")
    async def test_appends_user_and_assistant_to_history(self, mock_openai):
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Elaborate."))]
            )
        )
        s = InterviewSession("bot_003")
        initial_len = len(s._history)
        await s._generate("My design uses microservices.")
        assert len(s._history) == initial_len + 2
        assert s._history[-2]["role"] == "user"
        assert s._history[-1]["role"] == "assistant"

    @patch("app.bot_runner._openai")
    async def test_returns_fallback_on_api_error(self, mock_openai):
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=Exception("API rate limit")
        )
        s = InterviewSession("bot_003")
        result = await s._generate("Some input")
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("app.bot_runner._openai")
    async def test_sends_full_history_to_api(self, mock_openai):
        create_mock = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Next question."))]
            )
        )
        mock_openai.chat.completions.create = create_mock
        s = InterviewSession("bot_003")
        await s._generate("Turn 1")
        await s._generate("Turn 2")
        # Second call should pass 5 messages: system + user1 + assistant1 + user2
        last_call_messages = create_mock.call_args_list[-1][1]["messages"]
        roles = [m["role"] for m in last_call_messages]
        assert roles[0] == "system"
        assert roles.count("user") >= 2


# ── InterviewSession — _speak ─────────────────────────────────────────────────

class TestSpeak:
    @patch("app.bot_runner.recall_client")
    @patch("app.bot_runner._openai")
    async def test_sends_chat_message(self, mock_openai, mock_recall):
        mock_recall.send_chat_message = AsyncMock(return_value={})
        s = InterviewSession("bot_004")
        await s._speak("Where is your cache?")
        mock_recall.send_chat_message.assert_called_once()
        args = mock_recall.send_chat_message.call_args[0]
        assert "bot_004" == args[0]
        assert "Where is your cache?" in args[1]

    @patch("app.bot_runner.recall_client")
    @patch("app.bot_runner._openai")
    async def test_plays_audio_when_webhook_url_is_public(self, mock_openai, mock_recall):
        mock_recall.send_chat_message = AsyncMock(return_value={})
        mock_recall.play_media = AsyncMock(return_value={})
        fake_audio = b"\xff\xfb" + b"\x00" * 200
        mock_openai.audio.speech.create = AsyncMock(
            return_value=MagicMock(content=fake_audio)
        )

        s = InterviewSession("bot_004")
        # WEBHOOK_BASE_URL is already set to https:// in conftest
        await s._speak("What is your RTO?")
        mock_recall.play_media.assert_called_once()

    @patch("app.bot_runner.recall_client")
    async def test_does_not_raise_when_chat_message_fails(self, mock_recall):
        mock_recall.send_chat_message = AsyncMock(side_effect=Exception("Network error"))
        s = InterviewSession("bot_004")
        # Should swallow the error and not propagate
        await s._speak("Any question?")

    @patch("app.bot_runner.recall_client")
    @patch("app.bot_runner._openai")
    async def test_skips_play_media_for_localhost_url(self, mock_openai, mock_recall):
        mock_recall.send_chat_message = AsyncMock(return_value={})
        mock_recall.play_media = AsyncMock(return_value={})

        with patch("app.bot_runner.settings") as mock_settings:
            mock_settings.webhook_base_url = "http://localhost:8000"
            mock_settings.bot_persona_name = "System Design Interviewer"
            s = InterviewSession("bot_004")
            await s._speak("Where is your DB?")

        mock_recall.play_media.assert_not_called()


# ── InterviewSession — _analyse_screenshot ────────────────────────────────────

class TestAnalyseScreenshot:
    @patch("app.bot_runner._openai")
    async def test_returns_probe_question_on_success(self, mock_openai):
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Why no CDN?"))]
            )
        )
        s = InterviewSession("bot_005")
        result = await s._analyse_screenshot(b"\xff\xd8\xff" + b"\x00" * 50)
        assert result == "Why no CDN?"

    @patch("app.bot_runner._openai")
    async def test_returns_none_on_api_error(self, mock_openai):
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=Exception("Vision API down")
        )
        s = InterviewSession("bot_005")
        result = await s._analyse_screenshot(b"\xff\xd8\xff")
        assert result is None

    @patch("app.bot_runner._openai")
    async def test_encodes_image_as_base64(self, mock_openai):
        create_mock = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Single question."))]
            )
        )
        mock_openai.chat.completions.create = create_mock
        s = InterviewSession("bot_005")
        await s._analyse_screenshot(b"fakeimagedata")
        call_messages = create_mock.call_args[1]["messages"]
        image_content = call_messages[-1]["content"]
        # Find the image_url block
        image_block = next(b for b in image_content if b.get("type") == "image_url")
        assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ── InterviewSession — start / stop ──────────────────────────────────────────

class TestStartStop:
    @patch("app.bot_runner.recall_client")
    @patch("app.bot_runner._openai")
    async def test_start_calls_speak(self, mock_openai, mock_recall):
        mock_recall.send_chat_message = AsyncMock(return_value={})
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Hi, I am your interviewer."))]
            )
        )
        mock_openai.audio.speech.create = AsyncMock(
            return_value=MagicMock(content=b"\x00" * 100)
        )
        s = InterviewSession("bot_006")
        await s.start()
        mock_recall.send_chat_message.assert_called()

    async def test_stop_sets_inactive(self):
        s = InterviewSession("bot_006")
        await s.stop()
        assert s.is_active is False

    async def test_stop_cancels_screenshot_task(self):
        s = InterviewSession("bot_006")
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        s._screenshot_task = mock_task
        await s.stop()
        mock_task.cancel.assert_called_once()


# ── Session registry ──────────────────────────────────────────────────────────

class TestSessionRegistry:
    @patch("app.bot_runner.recall_client")
    @patch("app.bot_runner._openai")
    async def test_start_session_adds_to_registry(self, mock_openai, mock_recall):
        mock_recall.send_chat_message = AsyncMock(return_value={})
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Let's begin."))]
            )
        )
        mock_openai.audio.speech.create = AsyncMock(
            return_value=MagicMock(content=b"\x00" * 100)
        )
        await start_session("bot_reg_001")
        assert "bot_reg_001" in active_session_ids()

    @patch("app.bot_runner.recall_client")
    @patch("app.bot_runner._openai")
    async def test_start_session_idempotent(self, mock_openai, mock_recall):
        """Calling start_session twice for the same bot should not create duplicates."""
        mock_recall.send_chat_message = AsyncMock(return_value={})
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Begin."))]
            )
        )
        mock_openai.audio.speech.create = AsyncMock(
            return_value=MagicMock(content=b"\x00" * 100)
        )
        await start_session("bot_reg_002")
        await start_session("bot_reg_002")
        assert active_session_ids().count("bot_reg_002") == 1

    async def test_stop_session_removes_from_registry(self):
        s = InterviewSession("bot_reg_003")
        runner._sessions["bot_reg_003"] = s
        await stop_session("bot_reg_003")
        assert "bot_reg_003" not in active_session_ids()

    async def test_stop_nonexistent_session_is_noop(self):
        # Should not raise
        await stop_session("nonexistent_bot")

    async def test_handle_transcript_event_routes_to_session(self):
        mock_session = MagicMock()
        mock_session.push_transcript = MagicMock()
        runner._sessions["bot_reg_004"] = mock_session

        await handle_transcript_event("bot_reg_004", "Hello", "Alice")
        mock_session.push_transcript.assert_called_once_with("Hello", "Alice")

    async def test_handle_transcript_event_missing_bot_is_noop(self):
        # Should not raise when bot_id doesn't exist
        await handle_transcript_event("unknown_bot", "text", "Speaker")

    async def test_active_session_ids_returns_all(self):
        runner._sessions["a"] = MagicMock()
        runner._sessions["b"] = MagicMock()
        ids = active_session_ids()
        assert "a" in ids
        assert "b" in ids

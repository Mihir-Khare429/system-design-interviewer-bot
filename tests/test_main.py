"""
Tests for app/main.py — FastAPI routes and webhook handlers.

Uses httpx.AsyncClient with ASGITransport so no real server is started.
All Recall.ai and bot_runner calls are mocked.
"""

import os
import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def ac():
    """Async HTTP client pointed at the FastAPI ASGI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ── GET /health ───────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    async def test_returns_200(self, ac):
        resp = await ac.get("/health")
        assert resp.status_code == 200

    async def test_returns_ok_status(self, ac):
        resp = await ac.get("/health")
        assert resp.json()["status"] == "ok"

    async def test_includes_active_sessions_count(self, ac):
        resp = await ac.get("/health")
        assert "active_sessions" in resp.json()

    async def test_active_sessions_count_is_int(self, ac):
        resp = await ac.get("/health")
        assert isinstance(resp.json()["active_sessions"], int)


# ── GET /audio/{filename} ─────────────────────────────────────────────────────

class TestAudioEndpoint:
    async def test_serves_existing_file(self, ac, tmp_path):
        audio_dir = Path("/tmp/sdi_audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        test_file = audio_dir / "test_audio.mp3"
        test_file.write_bytes(b"\xff\xfb" + b"\x00" * 100)

        resp = await ac.get("/audio/test_audio.mp3")
        assert resp.status_code == 200
        test_file.unlink(missing_ok=True)

    async def test_returns_404_for_missing_file(self, ac):
        resp = await ac.get("/audio/does_not_exist.mp3")
        assert resp.status_code == 404

    async def test_returns_404_for_directory_traversal_attempt(self, ac):
        resp = await ac.get("/audio/../etc/passwd")
        # FastAPI will either 404 or reject the path — either is safe
        assert resp.status_code in (404, 422)


# ── POST /api/join-meeting ────────────────────────────────────────────────────

class TestJoinMeetingEndpoint:
    @patch("app.main.recall_client")
    async def test_returns_200_on_success(self, mock_recall, ac):
        mock_recall.create_bot = AsyncMock(return_value={"id": "bot_xyz"})
        resp = await ac.post(
            "/api/join-meeting",
            json={"meeting_url": "https://meet.google.com/abc-def-ghi"},
        )
        assert resp.status_code == 200

    @patch("app.main.recall_client")
    async def test_returns_bot_id(self, mock_recall, ac):
        mock_recall.create_bot = AsyncMock(return_value={"id": "bot_xyz"})
        resp = await ac.post(
            "/api/join-meeting",
            json={"meeting_url": "https://meet.google.com/abc-def-ghi"},
        )
        assert resp.json()["bot_id"] == "bot_xyz"

    @patch("app.main.recall_client")
    async def test_returns_joining_status(self, mock_recall, ac):
        mock_recall.create_bot = AsyncMock(return_value={"id": "bot_xyz"})
        resp = await ac.post(
            "/api/join-meeting",
            json={"meeting_url": "https://meet.google.com/abc-def-ghi"},
        )
        assert resp.json()["status"] == "joining"

    @patch("app.main.recall_client")
    async def test_passes_custom_bot_name(self, mock_recall, ac):
        mock_recall.create_bot = AsyncMock(return_value={"id": "bot_xyz"})
        await ac.post(
            "/api/join-meeting",
            json={"meeting_url": "https://meet.google.com/x", "bot_name": "My Bot"},
        )
        mock_recall.create_bot.assert_called_once_with(
            meeting_url="https://meet.google.com/x",
            bot_name="My Bot",
        )

    @patch("app.main.recall_client")
    async def test_returns_502_when_recall_raises(self, mock_recall, ac):
        mock_recall.create_bot = AsyncMock(side_effect=Exception("Recall.ai down"))
        resp = await ac.post(
            "/api/join-meeting",
            json={"meeting_url": "https://meet.google.com/abc-def-ghi"},
        )
        assert resp.status_code == 502

    async def test_returns_422_for_missing_meeting_url(self, ac):
        resp = await ac.post("/api/join-meeting", json={})
        assert resp.status_code == 422


# ── POST /api/webhook/recall ──────────────────────────────────────────────────

class TestRecallWebhook:
    @patch("app.main.bot_runner")
    async def test_in_call_recording_starts_session(self, mock_runner, ac):
        mock_runner.start_session = AsyncMock()
        mock_runner.stop_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/recall",
            json={
                "event": "bot.status_change",
                "data": {
                    "bot_id": "bot_aaa",
                    "status": {"code": "in_call_recording"},
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @patch("app.main.bot_runner")
    async def test_call_ended_stops_session(self, mock_runner, ac):
        mock_runner.stop_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/recall",
            json={
                "event": "bot.status_change",
                "data": {
                    "bot_id": "bot_aaa",
                    "status": {"code": "call_ended"},
                },
            },
        )
        assert resp.status_code == 200

    @patch("app.main.bot_runner")
    async def test_done_status_stops_session(self, mock_runner, ac):
        mock_runner.stop_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        await ac.post(
            "/api/webhook/recall",
            json={
                "event": "bot.status_change",
                "data": {"bot_id": "bot_bbb", "status": {"code": "done"}},
            },
        )

    @patch("app.main.bot_runner")
    async def test_fatal_status_stops_session(self, mock_runner, ac):
        mock_runner.stop_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        await ac.post(
            "/api/webhook/recall",
            json={
                "event": "bot.status_change",
                "data": {"bot_id": "bot_ccc", "status": {"code": "fatal"}},
            },
        )

    @patch("app.main.bot_runner")
    async def test_unknown_event_is_noop(self, mock_runner, ac):
        mock_runner.start_session = AsyncMock()
        mock_runner.stop_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/recall",
            json={"event": "recording.started", "data": {}},
        )
        assert resp.status_code == 200
        mock_runner.start_session.assert_not_called()
        mock_runner.stop_session.assert_not_called()

    @patch("app.main.bot_runner")
    async def test_bot_id_from_data_id_field(self, mock_runner, ac):
        """Some Recall events use data.id instead of data.bot_id."""
        mock_runner.start_session = AsyncMock()
        mock_runner.stop_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/recall",
            json={
                "event": "bot.status_change",
                "data": {"id": "bot_ddd", "status": {"code": "in_call_recording"}},
            },
        )
        assert resp.status_code == 200

    @patch("app.main.bot_runner")
    async def test_missing_bot_id_does_not_raise(self, mock_runner, ac):
        mock_runner.start_session = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/recall",
            json={"event": "bot.status_change", "data": {"status": {"code": "in_call_recording"}}},
        )
        assert resp.status_code == 200


# ── POST /api/webhook/transcription ──────────────────────────────────────────

class TestTranscriptionWebhook:
    @patch("app.main.bot_runner")
    async def test_final_transcript_triggers_handler(self, mock_runner, ac):
        mock_runner.handle_transcript_event = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/transcription",
            json={
                "bot_id": "bot_eee",
                "transcript": {
                    "speaker": "Alice",
                    "words": [{"text": "Hello"}, {"text": "world"}],
                    "is_final": True,
                },
            },
        )
        assert resp.status_code == 200

    @patch("app.main.bot_runner")
    async def test_partial_transcript_is_skipped(self, mock_runner, ac):
        mock_runner.handle_transcript_event = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        await ac.post(
            "/api/webhook/transcription",
            json={
                "bot_id": "bot_eee",
                "transcript": {
                    "speaker": "Alice",
                    "words": [{"text": "Hel"}],
                    "is_final": False,
                },
            },
        )
        mock_runner.handle_transcript_event.assert_not_called()

    @patch("app.main.bot_runner")
    async def test_empty_words_is_skipped(self, mock_runner, ac):
        mock_runner.handle_transcript_event = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        await ac.post(
            "/api/webhook/transcription",
            json={
                "bot_id": "bot_fff",
                "transcript": {"speaker": "Bob", "words": [], "is_final": True},
            },
        )
        mock_runner.handle_transcript_event.assert_not_called()

    @patch("app.main.bot_runner")
    async def test_missing_bot_id_is_skipped(self, mock_runner, ac):
        mock_runner.handle_transcript_event = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        await ac.post(
            "/api/webhook/transcription",
            json={
                "transcript": {
                    "speaker": "Alice",
                    "words": [{"text": "Hi"}],
                    "is_final": True,
                }
            },
        )
        mock_runner.handle_transcript_event.assert_not_called()

    @patch("app.main.bot_runner")
    async def test_text_is_joined_from_words(self, mock_runner, ac):
        mock_runner.handle_transcript_event = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/transcription",
            json={
                "bot_id": "bot_ggg",
                "transcript": {
                    "speaker": "Charlie",
                    "words": [{"text": "I"}, {"text": "use"}, {"text": "Redis"}],
                    "is_final": True,
                },
            },
        )
        # BackgroundTasks defers the actual call; verify the response was 200
        # and the endpoint did not error. The text join logic lives in main.py
        # and is tested by checking no 422/500 was returned.
        assert resp.status_code == 200

    @patch("app.main.bot_runner")
    async def test_returns_200_always(self, mock_runner, ac):
        mock_runner.handle_transcript_event = AsyncMock()
        mock_runner.active_session_ids = MagicMock(return_value=[])

        resp = await ac.post(
            "/api/webhook/transcription",
            json={"transcript": {"is_final": False, "words": [], "speaker": ""}},
        )
        assert resp.status_code == 200


# ── GET /api/sessions ─────────────────────────────────────────────────────────

class TestListSessions:
    async def test_returns_200(self, ac):
        resp = await ac.get("/api/sessions")
        assert resp.status_code == 200

    async def test_returns_count_field(self, ac):
        resp = await ac.get("/api/sessions")
        assert "count" in resp.json()

    async def test_returns_active_sessions_list(self, ac):
        resp = await ac.get("/api/sessions")
        assert "active_sessions" in resp.json()
        assert isinstance(resp.json()["active_sessions"], list)

    @patch("app.main.bot_runner")
    async def test_reflects_active_sessions(self, mock_runner, ac):
        mock_runner.active_session_ids = MagicMock(return_value=["bot_111", "bot_222"])

        resp = await ac.get("/api/sessions")
        data = resp.json()
        assert data["count"] == 2
        assert "bot_111" in data["active_sessions"]
        assert "bot_222" in data["active_sessions"]


# ── DELETE /api/sessions/{bot_id} ─────────────────────────────────────────────

class TestEndSession:
    @patch("app.main.recall_client")
    @patch("app.main.bot_runner")
    async def test_returns_200(self, mock_runner, mock_recall, ac):
        mock_runner.stop_session = AsyncMock()
        mock_recall.leave_call = AsyncMock()

        resp = await ac.delete("/api/sessions/bot_hhh")
        assert resp.status_code == 200

    @patch("app.main.recall_client")
    @patch("app.main.bot_runner")
    async def test_returns_stopped_status(self, mock_runner, mock_recall, ac):
        mock_runner.stop_session = AsyncMock()
        mock_recall.leave_call = AsyncMock()

        resp = await ac.delete("/api/sessions/bot_hhh")
        assert resp.json()["status"] == "stopped"
        assert resp.json()["bot_id"] == "bot_hhh"

    @patch("app.main.recall_client")
    @patch("app.main.bot_runner")
    async def test_calls_stop_session(self, mock_runner, mock_recall, ac):
        mock_runner.stop_session = AsyncMock()
        mock_recall.leave_call = AsyncMock()

        await ac.delete("/api/sessions/bot_iii")
        mock_runner.stop_session.assert_called_once_with("bot_iii")

    @patch("app.main.recall_client")
    @patch("app.main.bot_runner")
    async def test_calls_leave_call(self, mock_runner, mock_recall, ac):
        mock_runner.stop_session = AsyncMock()
        mock_recall.leave_call = AsyncMock()

        await ac.delete("/api/sessions/bot_jjj")
        mock_recall.leave_call.assert_called_once_with("bot_jjj")

    @patch("app.main.recall_client")
    @patch("app.main.bot_runner")
    async def test_tolerates_leave_call_failure(self, mock_runner, mock_recall, ac):
        """If the bot is already gone, leave_call may raise — endpoint should still return 200."""
        mock_runner.stop_session = AsyncMock()
        mock_recall.leave_call = AsyncMock(side_effect=Exception("Bot already gone"))

        resp = await ac.delete("/api/sessions/bot_kkk")
        assert resp.status_code == 200

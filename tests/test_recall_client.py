"""
Tests for app/recall_client.py — Recall.ai API wrapper.

All HTTP calls are intercepted with respx so no real network traffic is made.
"""

import pytest
import httpx
import respx
from unittest.mock import patch

from app.recall_client import RecallClient, _raise_for_status, RECALL_BASE_URL


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return RecallClient()


BOT_PAYLOAD = {
    "id": "bot_abc123",
    "meeting_url": "https://meet.google.com/xyz-abcd-efg",
    "status": {"code": "ready"},
}


# ── create_bot ────────────────────────────────────────────────────────────────

class TestCreateBot:
    @respx.mock
    async def test_creates_bot_successfully(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(200, json=BOT_PAYLOAD)
        )
        result = await client.create_bot("https://meet.google.com/xyz-abcd-efg")
        assert result["id"] == "bot_abc123"

    @respx.mock
    async def test_sends_correct_meeting_url(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(200, json=BOT_PAYLOAD)
        )
        await client.create_bot("https://meet.google.com/xyz-abcd-efg", bot_name="Tester")
        request_body = route.calls.last.request
        import json
        body = json.loads(request_body.content)
        assert body["meeting_url"] == "https://meet.google.com/xyz-abcd-efg"
        assert body["bot_name"] == "Tester"

    @respx.mock
    async def test_includes_transcription_webhook_url(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(200, json=BOT_PAYLOAD)
        )
        await client.create_bot("https://meet.google.com/abc")
        import json
        body = json.loads(route.calls.last.request.content)
        assert "/api/webhook/transcription" in body["real_time_transcription"]["destination_url"]

    @respx.mock
    async def test_includes_status_change_webhook_url(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(200, json=BOT_PAYLOAD)
        )
        await client.create_bot("https://meet.google.com/abc")
        import json
        body = json.loads(route.calls.last.request.content)
        assert "/api/webhook/recall" in body["status_change_webhook_url"]

    @respx.mock
    async def test_raises_on_401(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.create_bot("https://meet.google.com/abc")

    @respx.mock
    async def test_raises_on_500(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(500, json={"detail": "Server error"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.create_bot("https://meet.google.com/abc")

    @respx.mock
    async def test_default_bot_name(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot").mock(
            return_value=httpx.Response(200, json=BOT_PAYLOAD)
        )
        await client.create_bot("https://meet.google.com/abc")
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["bot_name"] == "System Design Interviewer"


# ── get_bot ───────────────────────────────────────────────────────────────────

class TestGetBot:
    @respx.mock
    async def test_returns_bot_data(self, client):
        respx.get(f"{RECALL_BASE_URL}/bot/bot_abc123").mock(
            return_value=httpx.Response(200, json=BOT_PAYLOAD)
        )
        result = await client.get_bot("bot_abc123")
        assert result["id"] == "bot_abc123"

    @respx.mock
    async def test_raises_on_404(self, client):
        respx.get(f"{RECALL_BASE_URL}/bot/nonexistent").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_bot("nonexistent")


# ── leave_call ────────────────────────────────────────────────────────────────

class TestLeaveCall:
    @respx.mock
    async def test_posts_to_leave_call_endpoint(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/leave_call").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.leave_call("bot_abc123")
        assert route.called

    @respx.mock
    async def test_raises_on_error(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/leave_call").mock(
            return_value=httpx.Response(422, json={"detail": "Already left"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.leave_call("bot_abc123")


# ── send_chat_message ─────────────────────────────────────────────────────────

class TestSendChatMessage:
    @respx.mock
    async def test_sends_message_successfully(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/send_chat_message").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await client.send_chat_message("bot_abc123", "Hello!")
        assert result == {"ok": True}

    @respx.mock
    async def test_sends_correct_message_body(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/send_chat_message").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.send_chat_message("bot_abc123", "Where is your CDN?")
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["message"] == "Where is your CDN?"

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/send_chat_message").mock(
            return_value=httpx.Response(400, json={"detail": "Bad request"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.send_chat_message("bot_abc123", "Hi")


# ── play_media ────────────────────────────────────────────────────────────────

class TestPlayMedia:
    @respx.mock
    async def test_posts_audio_url(self, client):
        route = respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/play_media").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.play_media("bot_abc123", "https://example.com/audio.mp3")
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["url"] == "https://example.com/audio.mp3"

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.post(f"{RECALL_BASE_URL}/bot/bot_abc123/play_media").mock(
            return_value=httpx.Response(422, json={"detail": "Invalid URL"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.play_media("bot_abc123", "not-a-url")


# ── get_screenshot ────────────────────────────────────────────────────────────

class TestGetScreenshot:
    @respx.mock
    async def test_returns_image_bytes_on_success(self, client):
        fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 100  # JPEG magic bytes
        respx.get(f"{RECALL_BASE_URL}/bot/bot_abc123/screenshot").mock(
            return_value=httpx.Response(200, content=fake_jpeg)
        )
        result = await client.get_screenshot("bot_abc123")
        assert result == fake_jpeg

    @respx.mock
    async def test_returns_empty_bytes_on_404(self, client):
        respx.get(f"{RECALL_BASE_URL}/bot/bot_abc123/screenshot").mock(
            return_value=httpx.Response(404)
        )
        result = await client.get_screenshot("bot_abc123")
        assert result == b""

    @respx.mock
    async def test_raises_on_server_error(self, client):
        respx.get(f"{RECALL_BASE_URL}/bot/bot_abc123/screenshot").mock(
            return_value=httpx.Response(500, json={"detail": "Internal error"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_screenshot("bot_abc123")


# ── _raise_for_status ─────────────────────────────────────────────────────────

class TestRaiseForStatus:
    def test_does_not_raise_on_200(self):
        req = httpx.Request("GET", "https://example.com")
        resp = httpx.Response(200, json={}, request=req)
        _raise_for_status(resp)  # should not raise

    def test_raises_on_400(self):
        req = httpx.Request("GET", "https://example.com")
        resp = httpx.Response(400, json={"detail": "bad"}, request=req)
        with pytest.raises(httpx.HTTPStatusError):
            _raise_for_status(resp)

    def test_raises_on_500(self):
        req = httpx.Request("GET", "https://example.com")
        resp = httpx.Response(500, json={"detail": "server error"}, request=req)
        with pytest.raises(httpx.HTTPStatusError):
            _raise_for_status(resp)

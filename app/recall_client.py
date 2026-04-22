"""
Recall.ai REST API client.
Docs: https://docs.recall.ai/reference/bot-create
"""

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

RECALL_BASE_URL = "https://us-west-2.recall.ai/api/v1"


class RecallClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Token {settings.recall_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Bot lifecycle
    # ------------------------------------------------------------------

    async def create_bot(
        self,
        meeting_url: str,
        bot_name: str = "System Design Interviewer",
    ) -> dict:
        """
        Create a Recall.ai bot and send it to join the specified meeting.

        The bot is configured to:
        - Stream real-time transcription to /api/webhook/transcription
        - Post status change events to /api/webhook/recall
        - Auto-leave if alone for 5 minutes
        """
        webhook_url = f"{settings.webhook_base_url}/api/webhook/recall"
        transcription_url = f"{settings.webhook_base_url}/api/webhook/transcription"

        payload = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
            "recording_config": {
                "transcript": {
                    "provider": {
                        "meeting_captions": {}
                    }
                },
                "realtime_endpoints": [
                    {
                        "type": "webhook",
                        "url": transcription_url,
                        "events": ["transcript.data"],
                    },
                ],
            },
            "status_change_webhook_url": webhook_url,
            "automatic_leave": {
                "waiting_room_timeout": 600,
                "noone_joined_timeout": 300,
                "everyone_left_timeout": {"timeout": 120},
            },
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{RECALL_BASE_URL}/bot",
                json=payload,
                headers=self._headers,
            )
            _raise_for_status(resp)
            bot = resp.json()
            logger.info("Bot created: id=%s meeting=%s", bot.get("id"), meeting_url)
            return bot

    async def get_bot(self, bot_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{RECALL_BASE_URL}/bot/{bot_id}",
                headers=self._headers,
            )
            _raise_for_status(resp)
            return resp.json()

    async def leave_call(self, bot_id: str) -> None:
        """Instruct the bot to leave the call immediately."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{RECALL_BASE_URL}/bot/{bot_id}/leave_call",
                headers=self._headers,
            )
            _raise_for_status(resp)
            logger.info("Bot %s instructed to leave call.", bot_id)

    # ------------------------------------------------------------------
    # In-meeting actions
    # ------------------------------------------------------------------

    async def send_chat_message(self, bot_id: str, message: str) -> dict:
        """
        Send a text message to the meeting's chat panel via the bot.
        Used as the primary output channel in local dev (no public audio URL needed).
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{RECALL_BASE_URL}/bot/{bot_id}/send_chat_message",
                json={"message": message},
                headers=self._headers,
            )
            _raise_for_status(resp)
            return resp.json()

    async def play_audio(self, bot_id: str, audio_bytes: bytes) -> dict:
        """Send raw MP3 bytes directly to the bot's audio output (base64-encoded)."""
        import base64
        b64 = base64.b64encode(audio_bytes).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{RECALL_BASE_URL}/bot/{bot_id}/output_audio",
                json={"kind": "mp3", "b64_data": b64},
                headers=self._headers,
            )
            _raise_for_status(resp)
            return resp.json()

    async def get_screenshot(self, bot_id: str) -> bytes:
        """
        Fetch the bot's current screen-share screenshot as raw bytes (JPEG).
        Returns empty bytes if the bot is not in a call or not recording.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{RECALL_BASE_URL}/bot/{bot_id}/screenshot",
                headers=self._headers,
            )
            if resp.status_code == 404:
                return b""
            _raise_for_status(resp)
            return resp.content


def _raise_for_status(resp: httpx.Response) -> None:
    """Raise a descriptive error that includes the response body."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Recall.ai API error %s: %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise


# Singleton instance used throughout the app
recall_client = RecallClient()

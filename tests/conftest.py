"""
Shared fixtures and configuration for the test suite.
"""

import os
import pytest

# ── Environment stubs ─────────────────────────────────────────────────────────
# Set env vars BEFORE any app module is imported so pydantic-settings picks them up.
os.environ.setdefault("RECALL_API_KEY", "test_recall_key")
os.environ.setdefault("OPENAI_API_KEY", "test_openai_key")
os.environ.setdefault("WEBHOOK_BASE_URL", "https://test.ngrok-free.app")
os.environ.setdefault("BOT_PERSONA_NAME", "System Design Interviewer")


@pytest.fixture(autouse=True)
def clear_bot_runner_sessions():
    """
    Reset the global session registry before every test so sessions don't
    bleed across test functions.
    """
    from app import bot_runner
    bot_runner._sessions.clear()
    yield
    bot_runner._sessions.clear()

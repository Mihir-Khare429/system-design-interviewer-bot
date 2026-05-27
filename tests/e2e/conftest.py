"""
E2E test infrastructure.

Sets DATABASE_URL to a temp SQLite file BEFORE any app module is imported
so the engine is created against the test DB, not the production one.
"""

import os
import tempfile

# ── Must come before any app import ─────────────────────────────────────────
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="sdi_e2e_")
os.close(_db_fd)

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"
os.environ.setdefault("RECALL_API_KEY", "e2e_test_recall_key")
os.environ.setdefault("OPENAI_API_KEY", "e2e_test_openai_key")
os.environ.setdefault("WEBHOOK_BASE_URL", "https://e2e-test.ngrok-free.app")
os.environ.setdefault("BOT_PERSONA_NAME", "System Design Interviewer")
os.environ["LLM_STREAMING"] = "false"  # simpler mock; streaming is unit-tested separately

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# ── Minimal fake audio (silent 100-byte webm-like blob) ──────────────────────
FAKE_AUDIO_BYTES = b"\x1a\x45\xdf\xa3" + b"\x00" * 96
FAKE_AUDIO_B64 = base64.b64encode(FAKE_AUDIO_BYTES).decode()

# Smallest valid MP3 frame so browser won't choke if it ever plays it
FAKE_MP3_BYTES = b"\xff\xfb\x90\x00" + b"\x00" * 104


# ── Mock factory helpers ──────────────────────────────────────────────────────

def _make_completion(text: str):
    c = MagicMock()
    c.choices[0].message.content = text
    c.usage = MagicMock(prompt_tokens=120, completion_tokens=40)
    return c


def _make_tts_response():
    r = MagicMock()
    r.content = FAKE_MP3_BYTES
    return r


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def llm_responses():
    """
    Canned LLM replies for the full interview.
    Each call to mock_openai.chat.completions.create pops the next entry.
    """
    # Exactly 14 entries: 13 interview turns + 1 scorecard.
    # Order: INTRO(3) + CONSTRAINTS(3) + CONSTRAINTS_TRIGGER(1)
    #        + DESIGN(3) + DESIGN_TRIGGER(1) + DEEP_DIVE(2) + SCORECARD(1)
    return [
        # INTRO — 3 exchanges
        "Nice to meet you! Tell me a bit about your background.",
        "Great experience. How have you handled large-scale data pipelines?",
        "Impressive. Let's jump into today's system design problem.",
        # CONSTRAINTS — response to each of the 3 clarifying questions
        "Good question — target 100k DAU, with peak 10x that.",
        "Eventual consistency is fine for most data; sessions need strong consistency.",
        "P99 read latency target is under 100 ms for the suggestion results.",
        # CONSTRAINTS TRIGGER — response when the timer fires
        "Storage budget is $50k/month; optimize for cost efficiency.",
        # DESIGN — 3 probing follow-ups
        "Good. How does your load balancer handle backend failover?",
        "Interesting. How do you handle replication lag in read replicas?",
        "Good. How would you partition the Kafka topics by user or event type?",
        # DESIGN TRIGGER — response when the design timer fires
        "Good point. What cache hit rate do you expect from the CDN layer?",
        # DEEP_DIVE — 2 stress-test follow-ups
        "Good. Now walk me through a full cascading failure scenario.",
        "Solid math. How does that storage cost scale at 10× user growth?",
        # SCORECARD — JSON returned by the scorecard LLM call
        '{"grade": "B+", "hire": "Lean Yes", "summary": "Solid design with good trade-off reasoning. Strong on infrastructure, could sharpen cost estimates.", "strengths": "Database layer, failure handling, async architecture", "gaps": "Cost estimation, CDN strategy underspecified", "study": "Consistent hashing, CAP theorem, cost optimization"}',
    ]


@pytest.fixture(scope="session")
def stt_transcripts():
    """Canned STT transcripts — one per audio chunk sent in the test."""
    # Exactly 13 entries: one per audio chunk the test sends.
    # Order: INTRO(3) + CONSTRAINTS(3) + CONSTRAINTS_TRIGGER(1)
    #        + DESIGN(3) + DESIGN_TRIGGER(1) + DEEP_DIVE(2)
    return [
        # INTRO — 3 candidate turns
        "I'm doing great, feeling ready for this.",
        "I have five years of backend experience with distributed systems at scale.",
        "I've designed data pipelines processing 10 million events per day.",
        # CONSTRAINTS — 3 clarifying questions
        "What are the expected daily active users?",
        "Does the system need strong or eventual consistency?",
        "What's the acceptable read latency at the 99th percentile?",
        # CONSTRAINTS TRIGGER — sent after the 1-second phase timer expires
        "Any constraints on the storage technology we can use?",
        # DESIGN — 3 design explanations
        "I'd start with a load balancer fronting stateless API servers.",
        "For storage I'd use PostgreSQL with read replicas and Redis for caching.",
        "For async workloads I'd use Kafka with consumer groups.",
        # DESIGN TRIGGER — sent after the 1-second phase timer expires
        "I'd also add a CDN layer to reduce origin load for static content.",
        # DEEP_DIVE — 2 stress-test answers
        "Circuit breakers between services, with exponential back-off retries.",
        "Storage estimate: 500 bytes per event times 10M events is about 5 GB per day.",
    ]


@pytest.fixture(scope="session")
def e2e_client(llm_responses, stt_transcripts):
    """
    TestClient with the full FastAPI app wired to a temp SQLite DB.
    LLM, Whisper, and TTS are mocked so tests are fast and offline.
    """
    llm_iter = iter(llm_responses)
    stt_iter = iter(stt_transcripts)

    def _next_completion(*args, **kwargs):
        return _make_completion(next(llm_iter, "Could you elaborate on that?"))

    def _next_transcript(*args, **kwargs):
        return next(stt_iter, "I see.")

    with (
        patch("app.ui_session._openai") as mock_llm,
        patch("app.ui_session._whisper") as mock_whisper,
        patch("app.ui_session._tts_client") as mock_tts,
    ):
        mock_llm.chat.completions.create = AsyncMock(side_effect=_next_completion)
        mock_whisper.audio.transcriptions.create = AsyncMock(side_effect=_next_transcript)
        mock_tts.audio.speech.create = AsyncMock(return_value=_make_tts_response())

        from app.main import app
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client


@pytest.fixture(scope="session")
def test_token(e2e_client):
    """Register a test user and return a valid JWT access token."""
    resp = e2e_client.post(
        "/api/auth/signup",
        json={"email": "e2e_test@example.com", "password": "E2eTestPass!99"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ── Teardown ─────────────────────────────────────────────────────────────────

def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_db_path)
    except OSError:
        pass

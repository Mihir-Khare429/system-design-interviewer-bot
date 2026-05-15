"""Per-session token + cost tracking. Used by UISession to record LLM/TTS/Whisper usage.

Sessions accumulate counters in memory; on session end (or each phase), we flush to DB
as a single update on the InterviewRun + append UsageEvent rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.config import settings


@dataclass
class CostMeter:
    """In-memory accumulator for a single interview session."""

    input_tokens: int = 0
    output_tokens: int = 0
    tts_chars: int = 0
    whisper_seconds: float = 0.0
    # Append-only events list — flushed to UsageEvent rows at end of session.
    events: list[dict] = field(default_factory=list)

    def record_llm(self, input_tokens: int, output_tokens: int) -> float:
        cost = (
            input_tokens * settings.price_input_per_1k / 1000.0
            + output_tokens * settings.price_output_per_1k / 1000.0
        )
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.events.append({
            "kind": "llm",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "units": 0,
            "cost_usd": cost,
        })
        return cost

    def record_tts(self, chars: int) -> float:
        cost = chars * settings.price_tts_per_1k_chars / 1000.0
        self.tts_chars += chars
        self.events.append({
            "kind": "tts",
            "input_tokens": 0,
            "output_tokens": 0,
            "units": float(chars),
            "cost_usd": cost,
        })
        return cost

    def record_whisper(self, audio_seconds: float) -> float:
        minutes = audio_seconds / 60.0
        cost = minutes * settings.price_whisper_per_minute
        self.whisper_seconds += audio_seconds
        self.events.append({
            "kind": "whisper",
            "input_tokens": 0,
            "output_tokens": 0,
            "units": audio_seconds,
            "cost_usd": cost,
        })
        return cost

    @property
    def total_cost_usd(self) -> float:
        return sum(e["cost_usd"] for e in self.events)


def estimate_tokens(text: str) -> int:
    """Cheap token estimate when the API doesn't return usage. ~4 chars/token."""
    return max(1, len(text) // 4)

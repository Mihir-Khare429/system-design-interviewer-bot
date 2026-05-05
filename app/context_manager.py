"""
Context prioritization for long interview conversations.

Every turn, instead of sending the full conversation history to the LLM,
we score each past exchange against the current user message using cosine
similarity over word frequencies (bag-of-words). Only the highest-scoring
chunks make it into the prompt, keeping the active context lean regardless
of how long the conversation runs.

Architecture:
  - System messages are ALWAYS kept (they carry phase/difficulty instructions).
  - The N most recent exchanges are ALWAYS kept (recency anchor).
  - All other user/assistant pairs are scored and the top-k are added until
    we hit the token budget.
  - Scoring runs in ~1ms pure Python — no external deps, no network calls.
"""

import math
import re
import time
import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# ── Tuning knobs ────────────────────────────────────────────────────────────

TOKEN_BUDGET = 1_500      # max tokens for the retrieved context window
RECENCY_ANCHOR = 4        # always include the last N non-system messages
WORDS_PER_TOKEN = 0.75    # conservative estimate (English ~0.75 words/token)
MIN_WORD_LEN = 2          # ignore single-char tokens in similarity scoring

# ── Helpers ──────────────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, return words ≥ MIN_WORD_LEN."""
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= MIN_WORD_LEN]


def _term_freq(words: list[str]) -> dict[str, float]:
    """Raw term-frequency vector (not normalised yet)."""
    tf: dict[str, float] = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1
    return tf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two TF dicts."""
    if not a or not b:
        return 0.0
    dot = sum(a.get(w, 0.0) * v for w, v in b.items())
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _approx_tokens(msg: dict) -> int:
    """Rough token count for a single message dict."""
    words = len((msg.get("content") or "").split())
    return max(4, int(words / WORDS_PER_TOKEN))


# ── Public API ───────────────────────────────────────────────────────────────


def prioritize(history: list[dict], current_user_text: str) -> list[dict]:
    """
    Return a pruned copy of *history* that fits within TOKEN_BUDGET.

    *history* must be the full conversation list including system messages
    (but NOT the current user turn — that's appended by the caller).

    The returned list preserves the original ordering so the LLM sees a
    coherent conversation rather than a randomly sampled one.
    """
    t0 = time.monotonic()

    system_msgs = [m for m in history if m["role"] == "system"]
    convo_msgs  = [m for m in history if m["role"] != "system"]

    # Nothing to trim if the conversation is still short
    if len(convo_msgs) <= RECENCY_ANCHOR * 2:
        logger.debug("context_manager: conversation short, passthrough")
        return history

    # Split into recency anchor (always kept) and candidate pool (scored)
    anchor   = convo_msgs[-RECENCY_ANCHOR:]
    pool     = convo_msgs[:-RECENCY_ANCHOR]

    # Score each message in the pool against the current user turn
    query_tf = _term_freq(_tokenize(current_user_text))
    scored: list[tuple[float, int, dict]] = []
    for idx, msg in enumerate(pool):
        sim = _cosine(query_tf, _term_freq(_tokenize(msg.get("content") or "")))
        scored.append((sim, idx, msg))

    # Sort by score descending; secondary sort by recency (higher idx = more recent)
    scored.sort(key=lambda x: (x[0], x[1] / max(len(pool), 1)), reverse=True)

    # Fill budget: system messages always in, then scored pool, then anchor
    system_tokens = sum(_approx_tokens(m) for m in system_msgs)
    anchor_tokens = sum(_approx_tokens(m) for m in anchor)
    remaining = TOKEN_BUDGET - system_tokens - anchor_tokens

    selected_pool: list[tuple[int, dict]] = []  # (original_idx, msg)
    for score, orig_idx, msg in scored:
        cost = _approx_tokens(msg)
        if remaining >= cost:
            selected_pool.append((orig_idx, msg))
            remaining -= cost
        if remaining <= 0:
            break

    # Re-sort selected pool by original index to preserve conversation order
    selected_pool.sort(key=lambda x: x[0])
    selected_msgs = [m for _, m in selected_pool]

    pruned = system_msgs + selected_msgs + anchor
    dropped = len(pool) - len(selected_pool)

    elapsed_ms = (time.monotonic() - t0) * 1000
    approx_tokens = sum(_approx_tokens(m) for m in pruned)
    logger.info(
        "context_manager: kept %d/%d pool msgs + %d anchor | ~%d tokens | dropped %d | %.1fms",
        len(selected_pool), len(pool), len(anchor), approx_tokens, dropped, elapsed_ms,
    )

    return pruned

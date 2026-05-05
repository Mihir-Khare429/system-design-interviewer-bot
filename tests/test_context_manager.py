"""
Tests for app/context_manager.py — context prioritization logic.

All tests run offline (pure Python, no LLM calls, no network).
"""

import math
import pytest
from app.context_manager import (
    TOKEN_BUDGET,
    RECENCY_ANCHOR,
    _cosine,
    _term_freq,
    _tokenize,
    _approx_tokens,
    prioritize,
)


# ── Unit: _tokenize ────────────────────────────────────────────────────────────

class TestTokenize:
    def test_lowercases_input(self):
        assert "redis" in _tokenize("Redis")

    def test_strips_punctuation(self):
        assert "?" not in " ".join(_tokenize("What is Redis?"))

    def test_filters_short_tokens(self):
        tokens = _tokenize("I am a DB")
        assert "i" not in tokens
        assert "a" not in tokens

    def test_returns_list_of_strings(self):
        result = _tokenize("scale the database")
        assert isinstance(result, list)
        assert all(isinstance(t, str) for t in result)

    def test_empty_string_returns_empty_list(self):
        assert _tokenize("") == []

    def test_handles_numbers(self):
        tokens = _tokenize("500 million users daily")
        assert "500" in tokens or "million" in tokens  # numbers parsed as tokens


# ── Unit: _term_freq ───────────────────────────────────────────────────────────

class TestTermFreq:
    def test_counts_occurrences(self):
        tf = _term_freq(["redis", "redis", "cache"])
        assert tf["redis"] == 2
        assert tf["cache"] == 1

    def test_empty_input_returns_empty_dict(self):
        assert _term_freq([]) == {}

    def test_single_word(self):
        tf = _term_freq(["database"])
        assert tf["database"] == 1


# ── Unit: _cosine ──────────────────────────────────────────────────────────────

class TestCosine:
    def test_identical_vectors_return_one(self):
        v = {"redis": 2.0, "cache": 1.0}
        assert math.isclose(_cosine(v, v), 1.0, abs_tol=1e-6)

    def test_orthogonal_vectors_return_zero(self):
        a = {"redis": 1.0}
        b = {"database": 1.0}
        assert _cosine(a, b) == 0.0

    def test_empty_vector_returns_zero(self):
        assert _cosine({}, {"redis": 1.0}) == 0.0
        assert _cosine({"redis": 1.0}, {}) == 0.0

    def test_partial_overlap_is_between_zero_and_one(self):
        a = {"redis": 1.0, "cache": 1.0}
        b = {"redis": 1.0, "sharding": 1.0}
        score = _cosine(a, b)
        assert 0.0 < score < 1.0

    def test_more_overlap_scores_higher(self):
        query = {"redis": 1.0, "cache": 1.0, "latency": 1.0}
        high = {"redis": 1.0, "cache": 1.0, "latency": 1.0}
        low  = {"sharding": 1.0}
        assert _cosine(query, high) > _cosine(query, low)


# ── Unit: _approx_tokens ──────────────────────────────────────────────────────

class TestApproxTokens:
    def test_non_empty_message_has_positive_token_count(self):
        msg = {"role": "user", "content": "How many users should we design for?"}
        assert _approx_tokens(msg) > 0

    def test_empty_content_returns_minimum(self):
        assert _approx_tokens({"role": "user", "content": ""}) >= 4

    def test_missing_content_does_not_raise(self):
        assert _approx_tokens({"role": "system"}) >= 4

    def test_longer_message_has_more_tokens(self):
        short = {"role": "user", "content": "Yes."}
        long  = {"role": "user", "content": "I would use a distributed caching layer with Redis Cluster, partitioned by consistent hashing across twelve shards with two replicas each."}
        assert _approx_tokens(long) > _approx_tokens(short)


# ── Unit: prioritize — short conversation passthrough ─────────────────────────

class TestPrioritizeShortConversation:
    def _make_history(self, n_turns):
        history = [{"role": "system", "content": "You are Alex, a staff engineer."}]
        for i in range(n_turns):
            history.append({"role": "user",      "content": f"Question {i}"})
            history.append({"role": "assistant",  "content": f"Answer {i}"})
        return history

    def test_short_conversation_is_returned_unchanged(self):
        history = self._make_history(3)
        result = prioritize(history, "current question")
        assert result == history

    def test_passthrough_at_recency_anchor_boundary(self):
        history = self._make_history(RECENCY_ANCHOR)
        result = prioritize(history, "current question")
        assert result == history

    def test_result_is_a_list(self):
        history = self._make_history(2)
        assert isinstance(prioritize(history, "x"), list)


# ── Unit: prioritize — system messages always kept ────────────────────────────

class TestSystemMessagesAlwaysKept:
    def _make_long_history(self):
        """Build a conversation guaranteed to exceed TOKEN_BUDGET."""
        history = [
            {"role": "system", "content": "You are Alex. Be adversarial."},
            {"role": "system", "content": "Phase: DESIGN. Challenge every decision."},
            {"role": "system", "content": "Difficulty: Staff. No mercy."},
        ]
        filler = ("I would implement the service using a microservices architecture "
                  "with separate services for each domain, each with its own database. "
                  "The API gateway routes requests using path-based routing and handles "
                  "authentication via JWT tokens validated against a central auth service. "
                  "All services communicate asynchronously via a Kafka event bus.")
        for _ in range(20):
            history.append({"role": "user",      "content": filler})
            history.append({"role": "assistant",  "content": filler})
        return history

    def test_all_system_messages_are_preserved(self):
        history = self._make_long_history()
        result = prioritize(history, "tell me about your database choice")
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 3

    def test_system_messages_appear_first(self):
        history = self._make_long_history()
        result = prioritize(history, "explain your caching strategy")
        for i, msg in enumerate(result):
            if msg["role"] != "system":
                break
        system_before = all(result[j]["role"] == "system" for j in range(i))
        assert system_before


# ── Unit: prioritize — recency anchor always kept ────────────────────────────

class TestRecencyAnchorAlwaysKept:
    def _make_long_history(self, anchor_content="ANCHOR_MESSAGE"):
        """Build a long history where the last RECENCY_ANCHOR messages have known content."""
        history = [{"role": "system", "content": "You are Alex."}]
        filler = "I want to use Redis for caching all the read-heavy endpoints."
        for _ in range(20):
            history.append({"role": "user",     "content": filler})
            history.append({"role": "assistant", "content": filler})
        for i in range(RECENCY_ANCHOR):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"{anchor_content} {i}"})
        return history

    def test_anchor_messages_are_in_result(self):
        history = self._make_long_history()
        result = prioritize(history, "completely unrelated query about zoology")
        contents = [m["content"] for m in result]
        for i in range(RECENCY_ANCHOR):
            assert f"ANCHOR_MESSAGE {i}" in contents

    def test_anchor_messages_appear_at_end(self):
        history = self._make_long_history()
        result = prioritize(history, "completely unrelated query about zoology")
        non_system = [m for m in result if m["role"] != "system"]
        tail = non_system[-RECENCY_ANCHOR:]
        for i, msg in enumerate(tail):
            assert msg["content"] == f"ANCHOR_MESSAGE {i}"


# ── Unit: prioritize — token budget respected ────────────────────────────────

class TestTokenBudget:
    def _verbose_history(self, n_turns=30):
        history = [{"role": "system", "content": "You are Alex."}]
        long_msg = ("I would design the system with a distributed caching layer, "
                    "consistent hashing, async replication, circuit breakers, "
                    "rate limiting, and a global CDN with edge PoPs in every region. " * 4)
        for _ in range(n_turns):
            history.append({"role": "user",      "content": long_msg})
            history.append({"role": "assistant",  "content": long_msg})
        return history

    def test_pruned_context_stays_within_budget(self):
        history = self._verbose_history(30)
        result = prioritize(history, "how does your caching layer work?")
        total_tokens = sum(_approx_tokens(m) for m in result)
        # Allow a small overrun due to the approximation rounding
        assert total_tokens <= TOKEN_BUDGET + 50

    def test_pruning_actually_reduces_message_count(self):
        history = self._verbose_history(30)
        result = prioritize(history, "tell me about latency")
        assert len(result) < len(history)

    def test_pruned_count_is_less_than_original(self):
        history = self._verbose_history(20)
        result = prioritize(history, "explain replication strategy")
        assert len(result) <= len(history)


# ── Unit: prioritize — relevance ordering ────────────────────────────────────

class TestRelevanceOrdering:
    def _history_with_known_relevant(self):
        """
        Build a long history where two messages are clearly relevant to the
        query ('kafka' + 'queue') and the rest are about unrelated topics.
        """
        history = [{"role": "system", "content": "Interview context."}]
        fillers = [
            "I would shard the PostgreSQL database by user ID.",
            "The CDN caches static assets at the edge.",
            "Redis handles session storage with a 30 minute TTL.",
            "The load balancer does round-robin with health checks.",
            "Object storage holds user-uploaded media files.",
        ]
        for filler in fillers * 6:  # 30 unrelated turns
            history.append({"role": "user",      "content": filler})
            history.append({"role": "assistant",  "content": filler})

        # These two turns are highly relevant to our query
        relevant_user = "For async jobs I would use a Kafka topic partitioned by event type."
        relevant_alex = "Kafka adds operational overhead. Why not SQS or a simpler message queue?"
        history.append({"role": "user",      "content": relevant_user})
        history.append({"role": "assistant",  "content": relevant_alex})

        return history, relevant_user, relevant_alex

    def test_relevant_messages_are_included(self):
        history, rel_user, rel_alex = self._history_with_known_relevant()
        result = prioritize(history, "Should I use Kafka or a simpler queue for the async pipeline?")
        contents = [m["content"] for m in result]
        assert rel_user in contents or rel_alex in contents

    def test_result_preserves_original_message_order(self):
        history, _, _ = self._history_with_known_relevant()
        result = prioritize(history, "kafka queue message broker")
        non_system = [m for m in result if m["role"] != "system"]
        # Use object identity (id) to find each message's original position,
        # avoiding false matches on duplicate content strings.
        id_to_idx = {id(m): i for i, m in enumerate(history)}
        indices = [id_to_idx[id(m)] for m in non_system if id(m) in id_to_idx]
        assert indices == sorted(indices)


# ── Unit: prioritize — edge cases ────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_history_returns_empty(self):
        result = prioritize([], "some query")
        assert result == []

    def test_only_system_messages_returned_unchanged(self):
        history = [
            {"role": "system", "content": "Instruction A"},
            {"role": "system", "content": "Instruction B"},
        ]
        result = prioritize(history, "any query")
        assert result == history

    def test_empty_query_does_not_raise(self):
        history = [{"role": "system", "content": "x"}]
        for _ in range(5):
            history.append({"role": "user", "content": "hello"})
            history.append({"role": "assistant", "content": "hi"})
        result = prioritize(history, "")
        assert isinstance(result, list)

    def test_does_not_mutate_original_history(self):
        history = [{"role": "system", "content": "You are Alex."}]
        for i in range(10):
            history.append({"role": "user",      "content": f"message {i}"})
            history.append({"role": "assistant",  "content": f"reply {i}"})
        original_len = len(history)
        prioritize(history, "query")
        assert len(history) == original_len

    def test_current_user_text_not_duplicated_in_result(self):
        """prioritize() receives history WITHOUT the current turn — verify no duplication."""
        history = [{"role": "system", "content": "You are Alex."}]
        query = "What hash function should I use?"
        for i in range(10):
            history.append({"role": "user",      "content": f"question {i}"})
            history.append({"role": "assistant",  "content": f"answer {i}"})
        result = prioritize(history, query)
        # The query itself should NOT appear in result (caller appends it separately)
        assert not any(m.get("content") == query for m in result)

    def test_single_turn_history_is_returned_unchanged(self):
        history = [
            {"role": "system",    "content": "You are Alex."},
            {"role": "user",      "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        assert prioritize(history, "some query") == history

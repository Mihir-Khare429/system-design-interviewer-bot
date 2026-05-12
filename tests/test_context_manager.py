"""
Tests for app/context_manager.py — context prioritization logic.

All tests run offline (pure Python, no LLM calls, no network).
"""

import math
import pytest
from app.context_manager import (
    TOKEN_BUDGET,
    RECENCY_ANCHOR,
    COSINE_WEIGHT,
    RECENCY_WEIGHT,
    _HAS_TIKTOKEN,
    _cosine,
    _term_freq,
    _tokenize,
    _approx_tokens,
    _build_idf,
    _tfidf_vec,
    _make_exchanges,
    stable_prefix_tokens,
    prioritize,
)


# ── _tokenize ──────────────────────────────────────────────────────────────────

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
        assert "million" in tokens


# ── _term_freq ─────────────────────────────────────────────────────────────────

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


# ── _cosine ────────────────────────────────────────────────────────────────────

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
        high  = {"redis": 1.0, "cache": 1.0, "latency": 1.0}
        low   = {"sharding": 1.0}
        assert _cosine(query, high) > _cosine(query, low)


# ── _approx_tokens ─────────────────────────────────────────────────────────────

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
        long  = {"role": "user", "content": (
            "I would use a distributed caching layer with Redis Cluster, "
            "partitioned by consistent hashing across twelve shards with two replicas each."
        )}
        assert _approx_tokens(long) > _approx_tokens(short)

    def test_tiktoken_gives_reasonable_count(self):
        # ~10 word sentence should be 10-20 tokens
        msg = {"role": "user", "content": "design a distributed url shortener at scale"}
        count = _approx_tokens(msg)
        assert 8 <= count <= 30


# ── _build_idf ─────────────────────────────────────────────────────────────────

class TestBuildIdf:
    def test_returns_dict_of_positive_floats(self):
        messages = [
            {"role": "user",      "content": "kafka latency sharding"},
            {"role": "assistant", "content": "why kafka specifically"},
        ]
        idf = _build_idf(messages)
        assert isinstance(idf, dict)
        assert all(v > 0 for v in idf.values())

    def test_rare_word_has_higher_idf_than_common_word(self):
        # "system" appears in every message; "kafka" appears in only one
        messages = [
            {"role": "user",      "content": "design the system using kafka"},
            {"role": "assistant", "content": "the system needs more detail"},
            {"role": "user",      "content": "the system handles writes"},
            {"role": "assistant", "content": "the system uses postgres"},
        ]
        idf = _build_idf(messages)
        assert idf.get("kafka", 0) > idf.get("system", 0)

    def test_word_in_every_message_has_lowest_idf(self):
        messages = [{"role": "user", "content": "redis redis redis"} for _ in range(10)]
        idf = _build_idf(messages)
        # "redis" appears in all 10 — idf = log(11/11) + 1 = 1.0 (minimum)
        assert idf.get("redis", 0) <= 1.05

    def test_empty_messages_returns_empty(self):
        assert _build_idf([]) == {}

    def test_single_message_returns_non_empty(self):
        messages = [{"role": "user", "content": "scale the database"}]
        idf = _build_idf(messages)
        assert len(idf) > 0

    def test_all_idf_values_at_least_one(self):
        # Smoothed IDF: log((N+1)/(df+1)) + 1 is always >= 1 when df <= N
        messages = [
            {"role": "user", "content": "redis cache latency"},
            {"role": "user", "content": "redis database writes"},
        ]
        idf = _build_idf(messages)
        assert all(v >= 1.0 for v in idf.values())


# ── _tfidf_vec ─────────────────────────────────────────────────────────────────

class TestTfidfVec:
    def test_rare_word_weighs_more_than_common_word(self):
        messages = [
            {"role": "user",      "content": "design the system with kafka"},
            {"role": "assistant", "content": "why the system needs kafka"},
            {"role": "user",      "content": "the system design question"},
            {"role": "assistant", "content": "the system handles this"},
        ]
        idf = _build_idf(messages)
        vec = _tfidf_vec(["kafka", "system", "the"], idf)
        # "kafka" is rare → higher tfidf; "the" is filtered by _tokenize anyway,
        # but "system" appears in every message → lower weight than "kafka"
        assert vec.get("kafka", 0) > vec.get("system", 0)

    def test_empty_words_returns_empty(self):
        idf = {"redis": 2.0}
        assert _tfidf_vec([], idf) == {}

    def test_unknown_word_uses_neutral_weight(self):
        idf = {"redis": 3.0}
        vec = _tfidf_vec(["unknownterm"], idf)
        # Unknown words fall back to idf=1.0
        assert vec.get("unknownterm") == 1.0


# ── _make_exchanges ────────────────────────────────────────────────────────────

class TestMakeExchanges:
    def test_user_assistant_pairs_grouped_together(self):
        msgs = [
            {"role": "user",      "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user",      "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ]
        exchanges = _make_exchanges(msgs)
        assert len(exchanges) == 2
        assert exchanges[0] == [msgs[0], msgs[1]]
        assert exchanges[1] == [msgs[2], msgs[3]]

    def test_odd_trailing_message_becomes_singleton(self):
        msgs = [
            {"role": "user",      "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user",      "content": "Q2"},  # no assistant reply yet
        ]
        exchanges = _make_exchanges(msgs)
        assert len(exchanges) == 2
        assert len(exchanges[1]) == 1
        assert exchanges[1][0]["content"] == "Q2"

    def test_empty_list_returns_empty(self):
        assert _make_exchanges([]) == []

    def test_single_message_becomes_singleton(self):
        msgs = [{"role": "user", "content": "hello"}]
        exchanges = _make_exchanges(msgs)
        assert len(exchanges) == 1
        assert len(exchanges[0]) == 1

    def test_preserves_original_order(self):
        msgs = [
            {"role": "user",      "content": "first"},
            {"role": "assistant", "content": "reply first"},
            {"role": "user",      "content": "second"},
            {"role": "assistant", "content": "reply second"},
        ]
        exchanges = _make_exchanges(msgs)
        assert exchanges[0][0]["content"] == "first"
        assert exchanges[1][0]["content"] == "second"

    def test_flattening_exchanges_recovers_original(self):
        msgs = [
            {"role": "user",      "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user",      "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ]
        flat = [m for ex in _make_exchanges(msgs) for m in ex]
        assert flat == msgs


# ── prioritize — short conversation passthrough ────────────────────────────────

class TestPrioritizeShortConversation:
    def _make_history(self, n_turns):
        history = [{"role": "system", "content": "You are Alex, a staff engineer."}]
        for i in range(n_turns):
            history.append({"role": "user",      "content": f"Question {i}"})
            history.append({"role": "assistant",  "content": f"Answer {i}"})
        return history

    def test_short_conversation_is_returned_unchanged(self):
        history = self._make_history(3)
        assert prioritize(history, "current question") == history

    def test_passthrough_at_recency_anchor_boundary(self):
        history = self._make_history(RECENCY_ANCHOR)
        assert prioritize(history, "current question") == history

    def test_result_is_a_list(self):
        history = self._make_history(2)
        assert isinstance(prioritize(history, "x"), list)


# ── prioritize — system messages always kept ───────────────────────────────────

class TestSystemMessagesAlwaysKept:
    def _make_long_history(self):
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
        assert len([m for m in result if m["role"] == "system"]) == 3

    def test_system_messages_appear_first(self):
        history = self._make_long_history()
        result = prioritize(history, "explain your caching strategy")
        first_non_system = next(i for i, m in enumerate(result) if m["role"] != "system")
        assert all(result[j]["role"] == "system" for j in range(first_non_system))


# ── prioritize — recency anchor always kept ────────────────────────────────────

class TestRecencyAnchorAlwaysKept:
    def _make_long_history(self, anchor_content="ANCHOR_MESSAGE"):
        history = [{"role": "system", "content": "You are Alex."}]
        filler = "I want to use Redis for caching all the read-heavy endpoints."
        for _ in range(20):
            history.append({"role": "user",      "content": filler})
            history.append({"role": "assistant",  "content": filler})
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


# ── prioritize — token budget respected ───────────────────────────────────────

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
        assert total_tokens <= TOKEN_BUDGET + 50  # small slack for per-message overhead rounding

    def test_pruning_actually_reduces_message_count(self):
        history = self._verbose_history(30)
        result = prioritize(history, "tell me about latency")
        assert len(result) < len(history)

    def test_pruned_count_is_less_than_original(self):
        history = self._verbose_history(20)
        result = prioritize(history, "explain replication strategy")
        assert len(result) <= len(history)


# ── prioritize — exchange-level pairing ───────────────────────────────────────

class TestExchangeLevelChunking:
    def _long_history_with_marker_exchange(self):
        """
        Build a long verbose history. The very last pool exchange (before the
        anchor) contains a uniquely identifiable user question and assistant
        answer. Verify they are either both in or both out of the result.
        """
        history = [{"role": "system", "content": "You are Alex."}]
        filler = ("I would shard the PostgreSQL database by user ID to distribute "
                  "load evenly and add read replicas for the query path. " * 3)
        for _ in range(15):
            history.append({"role": "user",      "content": filler})
            history.append({"role": "assistant",  "content": filler})
        # Marker exchange — placed so it ends up in the pool
        history.append({"role": "user",      "content": "MARKER_QUESTION about kafka streams"})
        history.append({"role": "assistant",  "content": "MARKER_ANSWER about kafka streams"})
        # Anchor (last RECENCY_ANCHOR messages)
        for i in range(RECENCY_ANCHOR):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"anchor {i}"})
        return history

    def test_exchange_pair_never_split(self):
        history = self._long_history_with_marker_exchange()
        result = prioritize(history, "kafka streams processing")
        contents = [m["content"] for m in result]
        question_in = "MARKER_QUESTION about kafka streams" in contents
        answer_in   = "MARKER_ANSWER about kafka streams" in contents
        # The pair must be kept together or dropped together
        assert question_in == answer_in

    def test_relevant_exchange_pair_both_present(self):
        history = self._long_history_with_marker_exchange()
        # Query directly about kafka — the marker exchange should score high enough to keep
        result = prioritize(history, "kafka streams processing pipeline")
        contents = [m["content"] for m in result]
        assert "MARKER_QUESTION about kafka streams" in contents
        assert "MARKER_ANSWER about kafka streams" in contents


# ── prioritize — recency-decay blending ───────────────────────────────────────

class TestRecencyBlending:
    def test_recent_exchange_beats_older_identical_exchange(self):
        """
        Two exchanges with identical content have the same cosine similarity score.
        The recency component must break the tie in favour of the more recent one.

        We use a budget tight enough to force exactly one exchange from the pool,
        then verify via object identity that it's the newer exchange, not the older.
        """
        history = [{"role": "system", "content": "You are Alex."}]
        identical = "sharding consistent hashing replication factor"

        # 6 filler exchanges, then older identical exchange, then 2 more fillers,
        # then newer identical exchange, then anchor.
        for _ in range(6):
            history.append({"role": "user",      "content": "unrelated filler about load balancer"})
            history.append({"role": "assistant",  "content": "unrelated filler about load balancer"})

        older_q = {"role": "user",      "content": identical}
        older_a = {"role": "assistant",  "content": identical}
        history.append(older_q)
        history.append(older_a)

        for _ in range(2):
            history.append({"role": "user",      "content": "unrelated filler about load balancer"})
            history.append({"role": "assistant",  "content": "unrelated filler about load balancer"})

        newer_q = {"role": "user",      "content": identical}
        newer_a = {"role": "assistant",  "content": identical}
        history.append(newer_q)
        history.append(newer_a)

        # Anchor
        for i in range(RECENCY_ANCHOR):
            history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"anchor {i}"})

        # Set budget tight enough that only ONE identical exchange fits.
        # Calculate the actual fixed costs so this test works whether tiktoken is
        # installed (accurate counts) or not (word-count heuristic fallback).
        from app import context_manager as cm

        system_tok = _approx_tokens({"role": "system", "content": "You are Alex."})
        anchor_tok = sum(
            _approx_tokens({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"anchor {i}",
            })
            for i in range(RECENCY_ANCHOR)
        )
        exchange_tok = _approx_tokens(older_q) + _approx_tokens(older_a)
        # Budget = fixed + one exchange + 2-token slack.
        # fixed + one_exchange + 2 < fixed + 2 * one_exchange  (always true when exchange_tok > 2)
        tight_budget = system_tok + anchor_tok + exchange_tok + 2

        original_budget = cm.TOKEN_BUDGET
        try:
            cm.TOKEN_BUDGET = tight_budget
            result = prioritize(history, "sharding consistent hashing")
        finally:
            cm.TOKEN_BUDGET = original_budget

        result_ids = {id(m) for m in result}

        # Exactly one of the two identical exchanges should appear
        older_in = id(older_q) in result_ids and id(older_a) in result_ids
        newer_in = id(newer_q) in result_ids and id(newer_a) in result_ids

        # They should not both be present (budget is too tight)
        assert not (older_in and newer_in), "Budget should have forced a choice between the two"
        # The newer exchange must be the one selected
        assert newer_in, "Recency blending should have selected the more recent exchange"

    def test_recency_and_cosine_weights_sum_to_one(self):
        assert math.isclose(COSINE_WEIGHT + RECENCY_WEIGHT, 1.0, abs_tol=1e-9)


# ── prioritize — TF-IDF signal improvement ────────────────────────────────────

class TestTfidfSignal:
    def test_domain_specific_term_scores_higher_than_filler(self):
        """
        An exchange mentioning 'kafka' in a corpus where 'kafka' is rare should
        score higher than an exchange full of common filler words, when the query
        is about kafka — even if the filler exchange is longer.
        """
        history = [{"role": "system", "content": "You are Alex."}]
        filler_msg = ("I would use the system with the design and the data and "
                      "the service to handle the load and the requests and the users "
                      "and the scale in the way that works for the architecture. " * 3)
        kafka_msg = "I would use kafka for async event streaming between services."

        for _ in range(8):
            history.append({"role": "user",      "content": filler_msg})
            history.append({"role": "assistant",  "content": filler_msg})
        history.append({"role": "user",      "content": kafka_msg})
        history.append({"role": "assistant",  "content": "Good. Why kafka over a simpler queue?"})
        for _ in range(4):
            history.append({"role": "user",      "content": filler_msg})
            history.append({"role": "assistant",  "content": filler_msg})
        # Anchor
        for i in range(RECENCY_ANCHOR):
            history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"anchor {i}"})

        result = prioritize(history, "tell me more about your kafka decision")
        contents = [m["content"] for m in result]
        assert kafka_msg in contents


# ── prioritize — edge cases ────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_history_returns_empty(self):
        assert prioritize([], "some query") == []

    def test_only_system_messages_returned_unchanged(self):
        history = [
            {"role": "system", "content": "Instruction A"},
            {"role": "system", "content": "Instruction B"},
        ]
        assert prioritize(history, "any query") == history

    def test_empty_query_does_not_raise(self):
        history = [{"role": "system", "content": "x"}]
        for _ in range(5):
            history.append({"role": "user",      "content": "hello"})
            history.append({"role": "assistant",  "content": "hi"})
        assert isinstance(prioritize(history, ""), list)

    def test_does_not_mutate_original_history(self):
        history = [{"role": "system", "content": "You are Alex."}]
        for i in range(10):
            history.append({"role": "user",      "content": f"message {i}"})
            history.append({"role": "assistant",  "content": f"reply {i}"})
        original_len = len(history)
        prioritize(history, "query")
        assert len(history) == original_len

    def test_current_user_text_not_duplicated_in_result(self):
        history = [{"role": "system", "content": "You are Alex."}]
        query = "What hash function should I use?"
        for i in range(10):
            history.append({"role": "user",      "content": f"question {i}"})
            history.append({"role": "assistant",  "content": f"answer {i}"})
        result = prioritize(history, query)
        assert not any(m.get("content") == query for m in result)

    def test_single_turn_history_is_returned_unchanged(self):
        history = [
            {"role": "system",    "content": "You are Alex."},
            {"role": "user",      "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        assert prioritize(history, "some query") == history

    def test_result_preserves_original_message_order(self):
        history = [{"role": "system", "content": "Interview context."}]
        fillers = [
            "I would shard the PostgreSQL database by user ID.",
            "The CDN caches static assets at the edge.",
            "Redis handles session storage with a 30 minute TTL.",
            "The load balancer does round-robin with health checks.",
            "Object storage holds user-uploaded media files.",
        ]
        for filler in fillers * 6:
            history.append({"role": "user",      "content": filler})
            history.append({"role": "assistant",  "content": filler})
        relevant_user = "For async jobs I would use a Kafka topic partitioned by event type."
        relevant_alex = "Kafka adds operational overhead. Why not SQS or a simpler message queue?"
        history.append({"role": "user",      "content": relevant_user})
        history.append({"role": "assistant",  "content": relevant_alex})

        result = prioritize(history, "kafka queue message broker")
        non_system = [m for m in result if m["role"] != "system"]
        id_to_idx = {id(m): i for i, m in enumerate(history)}
        indices = [id_to_idx[id(m)] for m in non_system if id(m) in id_to_idx]
        assert indices == sorted(indices)


# ── stable_prefix_tokens ──────────────────────────────────────────────────────

class TestStablePrefixTokens:
    def test_counts_leading_system_messages(self):
        history = [
            {"role": "system", "content": "You are Alex."},
            {"role": "system", "content": "Phase: INTRO."},
            {"role": "user", "content": "Hi"},
        ]
        count = stable_prefix_tokens(history)
        assert count > 0

    def test_stops_at_first_non_system_message(self):
        history = [
            {"role": "system", "content": "You are Alex."},
            {"role": "user", "content": "Hi there"},
            {"role": "system", "content": "After user — should not be counted"},
        ]
        count = stable_prefix_tokens(history)
        expected = _approx_tokens({"role": "system", "content": "You are Alex."})
        assert count == expected

    def test_all_system_messages_returns_full_sum(self):
        history = [
            {"role": "system", "content": "Instruction A"},
            {"role": "system", "content": "Instruction B"},
        ]
        count = stable_prefix_tokens(history)
        expected = sum(_approx_tokens(m) for m in history)
        assert count == expected

    def test_empty_history_returns_zero(self):
        assert stable_prefix_tokens([]) == 0

    def test_no_system_messages_returns_zero(self):
        history = [{"role": "user", "content": "Hello"}]
        assert stable_prefix_tokens(history) == 0

    def test_result_is_less_than_full_history_token_sum(self):
        history = [
            {"role": "system", "content": "You are Alex."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        prefix = stable_prefix_tokens(history)
        full = sum(_approx_tokens(m) for m in history)
        assert prefix < full


# ── tiktoken-specific ─────────────────────────────────────────────────────────

class TestTiktokenIntegration:
    def test_has_tiktoken_flag_is_bool(self):
        assert isinstance(_HAS_TIKTOKEN, bool)

    @pytest.mark.skipif(not _HAS_TIKTOKEN, reason="tiktoken not installed")
    def test_token_count_plausible_for_sentence(self):
        msg = {"role": "user", "content": "design a distributed URL shortener that handles 100k writes per second"}
        count = _approx_tokens(msg)
        # GPT tokenizer: ~15 words → ~18 tokens + 4 overhead = ~22. Allow wide range.
        assert 10 <= count <= 35

    @pytest.mark.skipif(not _HAS_TIKTOKEN, reason="tiktoken not installed")
    def test_budget_respected_with_exact_token_counts(self):
        history = [{"role": "system", "content": "You are Alex, a staff engineer."}]
        msg = ("I would build the service with a consistent hashing ring of "
               "256 virtual nodes distributed across 8 physical shards. "
               "Each shard has a primary and two async replicas.")
        for _ in range(30):
            history.append({"role": "user",      "content": msg})
            history.append({"role": "assistant",  "content": msg})
        result = prioritize(history, "explain your replication strategy")
        total = sum(_approx_tokens(m) for m in result)
        assert total <= TOKEN_BUDGET + 20

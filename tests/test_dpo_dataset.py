"""
Tests for data/dpo_dataset.jsonl — schema validation and quality checks.

No external dependencies required; pure Python JSON parsing only.
"""

import json
from pathlib import Path

import pytest

DATASET_PATH = Path(__file__).parent.parent / "data" / "dpo_dataset.jsonl"


def _load() -> list[dict]:
    with open(DATASET_PATH) as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ── Schema ─────────────────────────────────────────────────────────────────────

class TestDPODatasetSchema:
    def test_dataset_has_at_least_twenty_examples(self):
        assert len(_load()) >= 20

    def test_all_examples_have_required_keys(self):
        for i, ex in enumerate(_load()):
            for key in ("prompt", "chosen", "rejected"):
                assert key in ex, f"example {i} missing '{key}'"

    def test_prompt_is_a_list_of_dicts(self):
        for i, ex in enumerate(_load()):
            assert isinstance(ex["prompt"], list), f"example {i} prompt is not a list"
            for msg in ex["prompt"]:
                assert "role" in msg and "content" in msg, \
                    f"example {i} prompt message missing 'role' or 'content'"

    def test_chosen_is_single_element_assistant_list(self):
        for i, ex in enumerate(_load()):
            chosen = ex["chosen"]
            assert isinstance(chosen, list) and len(chosen) == 1, \
                f"example {i} chosen is not a length-1 list"
            assert chosen[0]["role"] == "assistant", \
                f"example {i} chosen[0] role is {chosen[0]['role']!r}"
            assert isinstance(chosen[0]["content"], str), \
                f"example {i} chosen[0] content is not a string"

    def test_rejected_is_single_element_assistant_list(self):
        for i, ex in enumerate(_load()):
            rejected = ex["rejected"]
            assert isinstance(rejected, list) and len(rejected) == 1, \
                f"example {i} rejected is not a length-1 list"
            assert rejected[0]["role"] == "assistant", \
                f"example {i} rejected[0] role is {rejected[0]['role']!r}"
            assert isinstance(rejected[0]["content"], str), \
                f"example {i} rejected[0] content is not a string"

    def test_all_prompts_start_with_system_message(self):
        for i, ex in enumerate(_load()):
            assert ex["prompt"][0]["role"] == "system", \
                f"example {i} prompt first role is {ex['prompt'][0]['role']!r}"

    def test_all_prompts_end_with_user_turn(self):
        for i, ex in enumerate(_load()):
            last_role = ex["prompt"][-1]["role"]
            assert last_role == "user", \
                f"example {i} prompt last role is {last_role!r} (expected 'user')"

    def test_chosen_and_rejected_responses_differ(self):
        for i, ex in enumerate(_load()):
            assert ex["chosen"][0]["content"] != ex["rejected"][0]["content"], \
                f"example {i} chosen == rejected (degenerate example)"

    def test_all_content_strings_are_non_empty(self):
        for i, ex in enumerate(_load()):
            for msg in ex["prompt"]:
                assert msg["content"].strip(), f"example {i} has empty prompt message"
            assert ex["chosen"][0]["content"].strip(),   f"example {i} chosen content empty"
            assert ex["rejected"][0]["content"].strip(), f"example {i} rejected content empty"

    def test_all_roles_are_valid(self):
        valid_roles = {"system", "user", "assistant"}
        for i, ex in enumerate(_load()):
            for msg in ex["prompt"]:
                assert msg["role"] in valid_roles, \
                    f"example {i} has invalid role {msg['role']!r}"

    def test_no_duplicate_examples(self):
        examples = _load()
        candidate_turns = [ex["prompt"][-1]["content"] for ex in examples]
        assert len(candidate_turns) == len(set(candidate_turns)), \
            "Dataset contains duplicate candidate turns"


# ── Quality ────────────────────────────────────────────────────────────────────

class TestDPODatasetQuality:
    def test_chosen_responses_are_brief(self):
        # Chosen probes should fit comfortably in 1-3 sentences (<= 90 words)
        for i, ex in enumerate(_load()):
            words = len(ex["chosen"][0]["content"].split())
            assert words <= 90, f"example {i} chosen too long: {words} words"

    def test_rejected_responses_are_longer_on_average(self):
        examples = _load()
        avg_chosen   = sum(len(ex["chosen"][0]["content"].split())   for ex in examples) / len(examples)
        avg_rejected = sum(len(ex["rejected"][0]["content"].split()) for ex in examples) / len(examples)
        assert avg_rejected > avg_chosen, (
            f"Rejected responses should be wordier on average. "
            f"chosen={avg_chosen:.1f} words, rejected={avg_rejected:.1f} words"
        )

    def test_majority_of_chosen_responses_end_with_question(self):
        examples = _load()
        without_q = [i for i, ex in enumerate(examples)
                     if not ex["chosen"][0]["content"].rstrip().endswith("?")]
        fail_rate = len(without_q) / len(examples)
        assert fail_rate <= 0.20, (
            f"{len(without_q)}/{len(examples)} chosen responses don't end with '?': "
            f"indices {without_q[:5]}"
        )

    def test_rejected_responses_are_more_verbose_than_chosen(self):
        # Rejected responses encode multi-topic verbosity in sentence count, not just "?"
        import re
        _split = re.compile(r"[.!?]+")

        def sentence_count(text: str) -> int:
            return len([s for s in _split.split(text) if len(s.split()) >= 3])

        examples = _load()
        avg_chosen_sents   = sum(sentence_count(ex["chosen"][0]["content"])   for ex in examples) / len(examples)
        avg_rejected_sents = sum(sentence_count(ex["rejected"][0]["content"]) for ex in examples) / len(examples)
        assert avg_rejected_sents > avg_chosen_sents, (
            f"Rejected responses should have more sentences on average. "
            f"chosen={avg_chosen_sents:.1f}, rejected={avg_rejected_sents:.1f}"
        )

    def test_no_markdown_in_chosen_responses(self):
        for i, ex in enumerate(_load()):
            text = ex["chosen"][0]["content"]
            assert "**" not in text, f"example {i} chosen has bold markdown"
            assert "```" not in text, f"example {i} chosen has code block"

    def test_candidate_turns_contain_technical_content(self):
        technical_keywords = {
            "hash", "redis", "mysql", "database", "cache", "shard", "kafka",
            "replicate", "ttl", "bucket", "sql", "cassandra", "zookeeper",
            "token", "index", "partition", "consistent", "fanout", "queue",
            "store", "table", "write", "read", "scale", "node", "cluster",
            "distributed", "sort", "leader", "replica", "sharding",
            "api", "transaction", "service", "latency", "throughput",
            "capacity", "users", "million", "error", "alert", "metrics",
        }
        for i, ex in enumerate(_load()):
            candidate = ex["prompt"][-1]["content"].lower()
            has_tech = any(kw in candidate for kw in technical_keywords)
            assert has_tech, (
                f"example {i} candidate turn seems to lack technical content: "
                f"{candidate[:100]!r}"
            )

    def test_system_prompt_mentions_alex_or_interviewer(self):
        for i, ex in enumerate(_load()):
            system_content = ex["prompt"][0]["content"].lower()
            assert "alex" in system_content or "interviewer" in system_content, \
                f"example {i} system prompt doesn't mention 'alex' or 'interviewer'"

    def test_no_hints_in_chosen_responses(self):
        # Chosen responses should never give away the answer
        giveaway_phrases = [
            "you should use", "you could use", "consider using",
            "a common pattern", "the standard approach",
        ]
        violations = []
        for i, ex in enumerate(_load()):
            text = ex["chosen"][0]["content"].lower()
            for phrase in giveaway_phrases:
                if phrase in text:
                    violations.append((i, phrase))
        assert len(violations) == 0, (
            f"Chosen responses contain hint phrases: {violations[:3]}"
        )

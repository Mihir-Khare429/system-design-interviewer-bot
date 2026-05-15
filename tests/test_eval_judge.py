"""
Tests for scripts/eval_judge.py — LLM-as-judge evaluation pipeline.

All network calls are mocked; no real API traffic is made.
Tests cover: Scores dataclass, PromptResult, _aggregate(), _judge() JSON
parsing, _print_summary(), and _build_parser() defaults.
"""

import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Import the module under test ───────────────────────────────────────────────

_SCRIPTS = str(Path(__file__).parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import eval_judge  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_result(
    base_mean: float,
    tuned_mean: float,
    idx: int = 0,
) -> eval_judge.PromptResult:
    """Build a PromptResult with uniform per-dimension scores that average to the given means."""
    q = base_mean
    r = tuned_mean
    return eval_judge.PromptResult(
        prompt_idx=idx,
        candidate_turn="candidate described their design",
        base_response="base model response here",
        tuned_response="fine-tuned model response here",
        base_scores=eval_judge.Scores(q, q, q, q),
        tuned_scores=eval_judge.Scores(r, r, r, r),
        base_wins=(base_mean > tuned_mean),
        tuned_wins=(tuned_mean > base_mean),
    )


# ── Scores ─────────────────────────────────────────────────────────────────────

class TestScores:
    def test_default_all_zeros(self):
        s = eval_judge.Scores()
        assert s.realism == 0.0
        assert s.challenge == 0.0
        assert s.conciseness == 0.0
        assert s.specificity == 0.0

    def test_mean_of_equal_scores(self):
        s = eval_judge.Scores(realism=3.0, challenge=3.0, conciseness=3.0, specificity=3.0)
        assert s.mean == pytest.approx(3.0)

    def test_mean_of_mixed_scores(self):
        s = eval_judge.Scores(realism=5.0, challenge=5.0, conciseness=1.0, specificity=1.0)
        assert s.mean == pytest.approx(3.0)

    def test_mean_of_all_zeros(self):
        assert eval_judge.Scores().mean == pytest.approx(0.0)

    def test_mean_of_max_scores(self):
        s = eval_judge.Scores(realism=5.0, challenge=5.0, conciseness=5.0, specificity=5.0)
        assert s.mean == pytest.approx(5.0)

    def test_scores_are_dataclass(self):
        # asdict works on dataclasses
        d = asdict(eval_judge.Scores(1.0, 2.0, 3.0, 4.0))
        assert d == {"realism": 1.0, "challenge": 2.0, "conciseness": 3.0, "specificity": 4.0}

    def test_scores_are_mutable(self):
        s = eval_judge.Scores()
        s.realism = 4.5
        assert s.realism == 4.5


# ── PromptResult ───────────────────────────────────────────────────────────────

class TestPromptResult:
    def test_win_flags_default_to_false(self):
        r = eval_judge.PromptResult(
            prompt_idx=0,
            candidate_turn="I'd shard by user ID",
            base_response="How many shards?",
            tuned_response="At what QPS does modulo sharding break?",
        )
        assert r.base_wins is False
        assert r.tuned_wins is False

    def test_win_flags_can_be_set(self):
        r = eval_judge.PromptResult(
            prompt_idx=1,
            candidate_turn="x",
            base_response="y",
            tuned_response="z",
            tuned_wins=True,
        )
        assert r.tuned_wins is True
        assert r.base_wins is False

    def test_scores_default_to_zero(self):
        r = eval_judge.PromptResult(
            prompt_idx=0, candidate_turn="", base_response="", tuned_response=""
        )
        assert r.base_scores.mean  == pytest.approx(0.0)
        assert r.tuned_scores.mean == pytest.approx(0.0)

    def test_is_dataclass(self):
        r = eval_judge.PromptResult(
            prompt_idx=7, candidate_turn="c", base_response="b", tuned_response="t"
        )
        assert asdict(r)["prompt_idx"] == 7


# ── _aggregate ─────────────────────────────────────────────────────────────────

class TestAggregate:
    def test_empty_results_returns_empty_dict(self):
        assert eval_judge._aggregate([]) == {}

    def test_returns_all_expected_keys(self):
        metrics = eval_judge._aggregate([_make_result(3.0, 4.0)])
        expected = {
            "base_realism_mean", "base_challenge_mean",
            "base_conciseness_mean", "base_specificity_mean", "base_overall_mean",
            "tuned_realism_mean", "tuned_challenge_mean",
            "tuned_conciseness_mean", "tuned_specificity_mean", "tuned_overall_mean",
            "tuned_win_rate", "base_win_rate", "tie_rate", "n_evaluated",
        }
        assert set(metrics.keys()) == expected

    def test_n_evaluated_matches_input(self):
        results = [_make_result(3.0, 4.0, i) for i in range(7)]
        assert eval_judge._aggregate(results)["n_evaluated"] == 7

    def test_win_rates_sum_to_one(self):
        results = [_make_result(3.0, 4.0, 0), _make_result(4.0, 3.0, 1), _make_result(3.0, 3.0, 2)]
        m = eval_judge._aggregate(results)
        assert m["tuned_win_rate"] + m["base_win_rate"] + m["tie_rate"] == pytest.approx(1.0, abs=1e-2)

    def test_tuned_wins_all(self):
        results = [_make_result(2.0, 5.0, i) for i in range(10)]
        m = eval_judge._aggregate(results)
        assert m["tuned_win_rate"] == pytest.approx(1.0)
        assert m["base_win_rate"]  == pytest.approx(0.0)
        assert m["tie_rate"]       == pytest.approx(0.0)

    def test_base_wins_all(self):
        results = [_make_result(5.0, 2.0, i) for i in range(4)]
        m = eval_judge._aggregate(results)
        assert m["base_win_rate"]  == pytest.approx(1.0)
        assert m["tuned_win_rate"] == pytest.approx(0.0)

    def test_all_ties(self):
        results = [_make_result(3.0, 3.0, i) for i in range(6)]
        m = eval_judge._aggregate(results)
        assert m["tie_rate"]       == pytest.approx(1.0)
        assert m["tuned_win_rate"] == pytest.approx(0.0)

    def test_mean_scores_are_correct(self):
        # base means: 2.0, 4.0 → average 3.0;  tuned means: 4.0 both → 4.0
        results = [_make_result(2.0, 4.0, 0), _make_result(4.0, 4.0, 1)]
        m = eval_judge._aggregate(results)
        assert m["base_overall_mean"]  == pytest.approx(3.0)
        assert m["tuned_overall_mean"] == pytest.approx(4.0)

    def test_single_result(self):
        m = eval_judge._aggregate([_make_result(4.0, 5.0)])
        assert m["n_evaluated"] == 1
        assert m["tuned_win_rate"] == pytest.approx(1.0)

    def test_all_means_are_non_negative(self):
        results = [_make_result(float(i % 5 + 1), float((i + 2) % 5 + 1), i) for i in range(10)]
        m = eval_judge._aggregate(results)
        for k, v in m.items():
            if k.endswith("_mean"):
                assert v >= 0.0, f"{k} is negative: {v}"

    def test_all_means_are_at_most_five(self):
        results = [_make_result(5.0, 5.0, i) for i in range(5)]
        m = eval_judge._aggregate(results)
        for k, v in m.items():
            if k.endswith("_mean"):
                assert v <= 5.0, f"{k} exceeds max: {v}"


# ── _judge JSON parsing ────────────────────────────────────────────────────────

class TestJudgeParsing:
    async def test_parses_well_formed_json(self):
        raw = '{"realism": 4, "challenge": 5, "conciseness": 3, "specificity": 4}'
        with patch("eval_judge._generate", new_callable=AsyncMock, return_value=raw):
            scores = await eval_judge._judge(MagicMock(), "gpt-4o", "candidate turn", "response")
        assert scores.realism     == pytest.approx(4.0)
        assert scores.challenge   == pytest.approx(5.0)
        assert scores.conciseness == pytest.approx(3.0)
        assert scores.specificity == pytest.approx(4.0)

    async def test_extracts_json_from_surrounding_text(self):
        raw = 'Sure! {"realism": 3, "challenge": 4, "conciseness": 5, "specificity": 2} Done.'
        with patch("eval_judge._generate", new_callable=AsyncMock, return_value=raw):
            scores = await eval_judge._judge(MagicMock(), "gpt-4o", "c", "r")
        assert scores.conciseness == pytest.approx(5.0)
        assert scores.specificity == pytest.approx(2.0)

    async def test_returns_zero_scores_on_completely_invalid_response(self):
        with patch("eval_judge._generate", new_callable=AsyncMock, return_value="no json here at all"):
            scores = await eval_judge._judge(MagicMock(), "gpt-4o", "c", "r")
        assert scores.mean == pytest.approx(0.0)

    async def test_returns_zero_scores_on_empty_response(self):
        with patch("eval_judge._generate", new_callable=AsyncMock, return_value=""):
            scores = await eval_judge._judge(MagicMock(), "gpt-4o", "c", "r")
        assert isinstance(scores, eval_judge.Scores)
        assert scores.mean == pytest.approx(0.0)

    async def test_handles_partial_json_gracefully(self):
        raw = '{"realism": 4}'
        with patch("eval_judge._generate", new_callable=AsyncMock, return_value=raw):
            scores = await eval_judge._judge(MagicMock(), "gpt-4o", "c", "r")
        assert scores.realism   == pytest.approx(4.0)
        assert scores.challenge == pytest.approx(0.0)  # missing key defaults to 0

    async def test_handles_float_scores(self):
        raw = '{"realism": 4.5, "challenge": 3.0, "conciseness": 5.0, "specificity": 2.5}'
        with patch("eval_judge._generate", new_callable=AsyncMock, return_value=raw):
            scores = await eval_judge._judge(MagicMock(), "gpt-4o", "c", "r")
        assert scores.realism == pytest.approx(4.5)
        assert scores.mean    == pytest.approx((4.5 + 3.0 + 5.0 + 2.5) / 4)

    async def test_judge_uses_correct_system_prompt(self):
        raw = '{"realism": 3, "challenge": 3, "conciseness": 3, "specificity": 3}'
        captured_messages = []

        async def capture(client, model, messages, **kwargs):
            captured_messages.extend(messages)
            return raw

        with patch("eval_judge._generate", side_effect=capture):
            await eval_judge._judge(MagicMock(), "gpt-4o", "candidate said X", "alex said Y")

        system_msgs = [m for m in captured_messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        content = system_msgs[0]["content"].lower()
        assert "evaluator" in content or "evaluate" in content or "assess" in content

    async def test_judge_prompt_includes_candidate_turn(self):
        raw = '{"realism": 3, "challenge": 3, "conciseness": 3, "specificity": 3}'
        captured_messages = []

        async def capture(client, model, messages, **kwargs):
            captured_messages.extend(messages)
            return raw

        with patch("eval_judge._generate", side_effect=capture):
            await eval_judge._judge(MagicMock(), "gpt-4o", "unique-candidate-phrase-xyz", "response")

        user_content = " ".join(m["content"] for m in captured_messages if m["role"] == "user")
        assert "unique-candidate-phrase-xyz" in user_content


# ── _print_summary ─────────────────────────────────────────────────────────────

class TestPrintSummary:
    def _full_metrics(self) -> dict:
        return {
            "base_realism_mean": 3.0,     "base_challenge_mean": 2.5,
            "base_conciseness_mean": 3.5, "base_specificity_mean": 3.0,
            "base_overall_mean": 3.0,
            "tuned_realism_mean": 4.0,    "tuned_challenge_mean": 4.5,
            "tuned_conciseness_mean": 4.0, "tuned_specificity_mean": 4.5,
            "tuned_overall_mean": 4.25,
            "tuned_win_rate": 0.7, "base_win_rate": 0.2, "tie_rate": 0.1,
            "n_evaluated": 10,
        }

    def test_prints_all_four_dimensions(self, capsys):
        eval_judge._print_summary(self._full_metrics())
        out = capsys.readouterr().out.lower()
        assert "realism"     in out
        assert "challenge"   in out
        assert "conciseness" in out
        assert "specificity" in out

    def test_prints_win_rate(self, capsys):
        eval_judge._print_summary(self._full_metrics())
        out = capsys.readouterr().out.lower()
        assert "win rate" in out

    def test_prints_evaluation_count(self, capsys):
        eval_judge._print_summary(self._full_metrics())
        assert "10" in capsys.readouterr().out

    def test_does_not_raise_on_empty_metrics(self):
        eval_judge._print_summary({})  # must not raise

    def test_does_not_raise_on_missing_keys(self):
        eval_judge._print_summary({"n_evaluated": 5})  # must not raise


# ── _build_parser ──────────────────────────────────────────────────────────────

class TestBuildParser:
    def _parse(self, *argv):
        return eval_judge._build_parser().parse_args(list(argv))

    def test_default_judge_model(self):
        assert self._parse().judge_model == eval_judge.DEFAULT_JUDGE_MODEL

    def test_default_base_model(self):
        assert self._parse().base_model == eval_judge.DEFAULT_BASE_MODEL

    def test_default_tuned_model(self):
        assert self._parse().tuned_model == "sdi-interviewer"

    def test_default_n_eval(self):
        assert self._parse().n_eval == 10

    def test_default_run_id_is_none(self):
        assert self._parse().run_id is None

    def test_default_tuned_url_is_none(self):
        assert self._parse().tuned_url is None

    def test_default_mlflow_uri(self):
        assert self._parse().mlflow_uri == "./mlruns"

    def test_default_dataset_path(self):
        assert str(self._parse().dataset).endswith("dpo_dataset.jsonl")

    def test_default_openai_api_key_is_none(self):
        assert self._parse().openai_api_key is None

    def test_override_tuned_model(self):
        assert self._parse("--tuned-model", "my-ft-model").tuned_model == "my-ft-model"

    def test_override_n_eval(self):
        assert self._parse("--n-eval", "5").n_eval == 5

    def test_override_run_id(self):
        assert self._parse("--run-id", "abc123xyz").run_id == "abc123xyz"

    def test_override_judge_model(self):
        assert self._parse("--judge-model", "gpt-4o-mini").judge_model == "gpt-4o-mini"

    def test_override_tuned_url(self):
        args = self._parse("--tuned-url", "http://localhost:11434/v1")
        assert args.tuned_url == "http://localhost:11434/v1"

    def test_parser_rejects_unknown_flag(self):
        with pytest.raises(SystemExit):
            self._parse("--nonexistent-option")


# ── Judge template ─────────────────────────────────────────────────────────────

class TestJudgeTemplate:
    def test_template_formats_without_error(self):
        rendered = eval_judge._JUDGE_TEMPLATE.format(
            candidate_turn="I'd use Redis for caching",
            response="At what throughput does Redis become your bottleneck?",
        )
        assert "I'd use Redis" in rendered
        assert "bottleneck?" in rendered

    def test_template_contains_all_four_dimensions(self):
        rendered = eval_judge._JUDGE_TEMPLATE.format(
            candidate_turn="x", response="y"
        )
        for dim in ("realism", "challenge", "conciseness", "specificity"):
            assert dim in rendered.lower()

    def test_template_asks_for_json_output(self):
        rendered = eval_judge._JUDGE_TEMPLATE.format(
            candidate_turn="x", response="y"
        )
        assert "json" in rendered.lower()

    def test_system_prompt_is_non_empty(self):
        assert len(eval_judge._JUDGE_SYSTEM.strip()) > 0

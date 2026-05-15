#!/usr/bin/env python3
"""
Before/after evaluation of the DPO fine-tuned interviewer using LLM-as-judge.

Generates responses from two models (base and fine-tuned) for each eval
prompt, then asks a judge LLM to score both responses on four dimensions:

  • realism      — sounds like a real senior engineer, not a chatbot (1–5)
  • challenge    — tests the candidate without hinting at the answer (1–5)
  • conciseness  — appropriately brief, one question per turn (1–5)
  • specificity  — targets what the candidate actually said (1–5)

Aggregate metrics (mean scores per dimension, win rate) are logged to MLflow
alongside the full per-prompt breakdown so you can drill into failure cases.

Both models are called via OpenAI-compatible chat completion endpoints — the
same interface the app uses — so you can point this at Ollama, vLLM, or the
OpenAI API interchangeably.

Usage
-----
  # Compare Ollama base vs fine-tuned (after running llm_setup.py):
  python scripts/eval_judge.py \\
      --base-url http://localhost:11434/v1 \\
      --base-model llama3.2:3b-instruct    \\
      --tuned-model sdi-interviewer

  # Compare GPT-4o-mini vs the fine-tuned model (mixed provider):
  python scripts/eval_judge.py \\
      --base-url https://api.openai.com/v1 \\
      --base-model gpt-4o-mini             \\
      --tuned-url http://localhost:11434/v1 \\
      --tuned-model sdi-interviewer

  # Attach results to an existing MLflow training run:
  python scripts/eval_judge.py --run-id <run_id>
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths & defaults ──────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT  = _SCRIPT_DIR.parent
DATA_PATH   = _REPO_ROOT / "data" / "dpo_dataset.jsonl"

DEFAULT_BASE_URL   = "https://api.openai.com/v1"
DEFAULT_BASE_MODEL = "gpt-4o-mini"
DEFAULT_JUDGE_MODEL = "gpt-4o"
MAX_EVAL_TOKENS    = 120
MLFLOW_EXPERIMENT  = "sdi-dpo"

# ── Judge scoring prompt ──────────────────────────────────────────────────────

_JUDGE_SYSTEM = (
    "You are an expert evaluator assessing AI-generated responses from a "
    "system design interviewer (Alex, a Senior Staff Engineer). "
    "You rate responses numerically and return JSON only."
)

_JUDGE_TEMPLATE = """
Evaluate the following interviewer response on four dimensions (score 1–5):

  realism     — Sounds like a real senior engineer, not a generic chatbot.
                (1 = robotic/formulaic, 5 = completely natural and human)
  challenge   — Appropriately tests the candidate without giving hints.
                (1 = too easy or telegraphs the answer, 5 = sharp targeted probe)
  conciseness — Appropriately brief; one focused question per turn.
                (1 = verbose/multi-part, 5 = perfectly tight)
  specificity — Directly addresses what the candidate actually said.
                (1 = generic filler, 5 = laser-targeted to candidate's specific claim)

Context (what the candidate just said):
{candidate_turn}

Interviewer response to evaluate:
{response}

Reply with ONLY a JSON object, no explanation:
{{"realism": <1-5>, "challenge": <1-5>, "conciseness": <1-5>, "specificity": <1-5>}}
""".strip()


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Scores:
    realism:     float = 0.0
    challenge:   float = 0.0
    conciseness: float = 0.0
    specificity: float = 0.0

    @property
    def mean(self) -> float:
        return statistics.mean([self.realism, self.challenge, self.conciseness, self.specificity])


@dataclass
class PromptResult:
    prompt_idx:    int
    candidate_turn: str
    base_response:  str
    tuned_response: str
    base_scores:    Scores = field(default_factory=Scores)
    tuned_scores:   Scores = field(default_factory=Scores)
    base_wins:      bool   = False  # tuned scored higher overall
    tuned_wins:     bool   = False  # tuned scored higher overall


# ── Model inference ───────────────────────────────────────────────────────────

async def _generate(
    client,
    model: str,
    messages: list[dict],
    max_tokens: int = MAX_EVAL_TOKENS,
) -> str:
    """Call the chat completions endpoint and return the assistant text."""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.85,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Generation failed for model %s: %s", model, exc)
        return ""


# ── Judge ─────────────────────────────────────────────────────────────────────

async def _judge(judge_client, judge_model: str, candidate_turn: str, response: str) -> Scores:
    """Ask the judge to score a single interviewer response."""
    prompt = _JUDGE_TEMPLATE.format(candidate_turn=candidate_turn, response=response)
    raw = await _generate(judge_client, judge_model, [
        {"role": "system",  "content": _JUDGE_SYSTEM},
        {"role": "user",    "content": prompt},
    ], max_tokens=60)

    try:
        m = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        return Scores(
            realism=float(data.get("realism", 0)),
            challenge=float(data.get("challenge", 0)),
            conciseness=float(data.get("conciseness", 0)),
            specificity=float(data.get("specificity", 0)),
        )
    except Exception as exc:
        logger.warning("Failed to parse judge output %r: %s", raw, exc)
        return Scores()


# ── Evaluation loop ───────────────────────────────────────────────────────────

async def evaluate(args: argparse.Namespace) -> list[PromptResult]:
    from openai import AsyncOpenAI

    # Load eval prompts from the dataset (last N examples make a clean eval set)
    prompts: list[dict] = []
    with open(args.dataset) as fh:
        for line in fh:
            line = line.strip()
            if line:
                prompts.append(json.loads(line))

    eval_prompts = prompts[-args.n_eval:]
    logger.info("Evaluating on %d prompts.", len(eval_prompts))

    # Clients — base model and fine-tuned model may be at different URLs
    base_client = AsyncOpenAI(
        api_key=args.openai_api_key or "ollama",
        base_url=args.base_url,
    )
    tuned_client = AsyncOpenAI(
        api_key=args.openai_api_key or "ollama",
        base_url=args.tuned_url or args.base_url,
    )
    judge_client = AsyncOpenAI(api_key=args.openai_api_key)

    results: list[PromptResult] = []

    for idx, example in enumerate(eval_prompts):
        prompt_msgs: list[dict] = example["prompt"]

        # Extract the last user turn as the "candidate turn" for display
        candidate_turns = [m["content"] for m in prompt_msgs if m["role"] == "user"]
        candidate_turn  = candidate_turns[-1] if candidate_turns else ""

        logger.info("[%d/%d] Generating responses…", idx + 1, len(eval_prompts))

        base_resp  = await _generate(base_client,  args.base_model,  prompt_msgs)
        tuned_resp = await _generate(tuned_client, args.tuned_model, prompt_msgs)

        if not base_resp or not tuned_resp:
            logger.warning("Skipping prompt %d — empty generation.", idx)
            continue

        logger.info("[%d/%d] Judging responses…", idx + 1, len(eval_prompts))
        base_scores  = await _judge(judge_client, args.judge_model, candidate_turn, base_resp)
        tuned_scores = await _judge(judge_client, args.judge_model, candidate_turn, tuned_resp)

        result = PromptResult(
            prompt_idx=idx,
            candidate_turn=candidate_turn,
            base_response=base_resp,
            tuned_response=tuned_resp,
            base_scores=base_scores,
            tuned_scores=tuned_scores,
            base_wins=(base_scores.mean > tuned_scores.mean),
            tuned_wins=(tuned_scores.mean > base_scores.mean),
        )
        results.append(result)

        logger.info(
            "  Base  — mean %.2f  (R:%.1f C:%.1f Cn:%.1f S:%.1f)",
            base_scores.mean,
            base_scores.realism, base_scores.challenge,
            base_scores.conciseness, base_scores.specificity,
        )
        logger.info(
            "  Tuned — mean %.2f  (R:%.1f C:%.1f Cn:%.1f S:%.1f)",
            tuned_scores.mean,
            tuned_scores.realism, tuned_scores.challenge,
            tuned_scores.conciseness, tuned_scores.specificity,
        )

    return results


# ── Aggregation & logging ─────────────────────────────────────────────────────

def _aggregate(results: list[PromptResult]) -> dict:
    if not results:
        return {}

    def _mean(vals):
        return round(statistics.mean(vals), 3) if vals else 0.0

    base_r   = [r.base_scores.realism     for r in results]
    base_ch  = [r.base_scores.challenge   for r in results]
    base_cn  = [r.base_scores.conciseness for r in results]
    base_sp  = [r.base_scores.specificity for r in results]
    tuned_r  = [r.tuned_scores.realism     for r in results]
    tuned_ch = [r.tuned_scores.challenge   for r in results]
    tuned_cn = [r.tuned_scores.conciseness for r in results]
    tuned_sp = [r.tuned_scores.specificity for r in results]

    n_tuned_wins = sum(1 for r in results if r.tuned_wins)
    n_base_wins  = sum(1 for r in results if r.base_wins)
    n_ties       = len(results) - n_tuned_wins - n_base_wins

    return {
        "base_realism_mean":       _mean(base_r),
        "base_challenge_mean":     _mean(base_ch),
        "base_conciseness_mean":   _mean(base_cn),
        "base_specificity_mean":   _mean(base_sp),
        "base_overall_mean":       _mean(base_r + base_ch + base_cn + base_sp),
        "tuned_realism_mean":      _mean(tuned_r),
        "tuned_challenge_mean":    _mean(tuned_ch),
        "tuned_conciseness_mean":  _mean(tuned_cn),
        "tuned_specificity_mean":  _mean(tuned_sp),
        "tuned_overall_mean":      _mean(tuned_r + tuned_ch + tuned_cn + tuned_sp),
        "tuned_win_rate":          round(n_tuned_wins / len(results), 3),
        "base_win_rate":           round(n_base_wins  / len(results), 3),
        "tie_rate":                round(n_ties        / len(results), 3),
        "n_evaluated":             len(results),
    }


def log_to_mlflow(
    results: list[PromptResult],
    metrics: dict,
    args: argparse.Namespace,
) -> None:
    import mlflow

    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    ctx = (
        mlflow.start_run(run_id=args.run_id)
        if args.run_id
        else mlflow.start_run(run_name=f"eval-{args.tuned_model}")
    )
    with ctx:
        mlflow.log_params({
            "eval_base_model":   args.base_model,
            "eval_tuned_model":  args.tuned_model,
            "eval_judge_model":  args.judge_model,
            "eval_n_prompts":    len(results),
            "eval_dataset":      str(args.dataset),
        })
        mlflow.log_metrics(metrics)

        # Per-prompt breakdown as a JSON artifact for drill-down analysis
        breakdown = [
            {
                "prompt_idx":     r.prompt_idx,
                "candidate_turn": r.candidate_turn,
                "base_response":  r.base_response,
                "tuned_response": r.tuned_response,
                "base_scores":    asdict(r.base_scores),
                "tuned_scores":   asdict(r.tuned_scores),
                "winner":         "tuned" if r.tuned_wins else ("base" if r.base_wins else "tie"),
            }
            for r in results
        ]
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="eval_breakdown_"
        ) as tmp:
            json.dump(breakdown, tmp, indent=2)
            tmp_path = tmp.name
        mlflow.log_artifact(tmp_path, artifact_path="eval")
        os.unlink(tmp_path)

        run_id = mlflow.active_run().info.run_id
        logger.info("MLflow run: %s", run_id)


def _print_summary(metrics: dict) -> None:
    print("\n" + "=" * 62)
    print("  Evaluation Summary")
    print("=" * 62)
    dims = ["realism", "challenge", "conciseness", "specificity"]
    print(f"  {'Dimension':<14}  {'Base':>6}  {'Tuned':>6}  {'Delta':>7}")
    print("  " + "-" * 42)
    for dim in dims:
        base  = metrics.get(f"base_{dim}_mean",  0)
        tuned = metrics.get(f"tuned_{dim}_mean", 0)
        delta = tuned - base
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "–")
        print(f"  {dim:<14}  {base:>6.2f}  {tuned:>6.2f}  {arrow}{abs(delta):>5.2f}")
    print("  " + "-" * 42)
    print(f"  {'Overall':<14}  {metrics.get('base_overall_mean', 0):>6.2f}  "
          f"{metrics.get('tuned_overall_mean', 0):>6.2f}")
    print()
    print(f"  Win rate  — Tuned: {metrics.get('tuned_win_rate', 0):.1%}  "
          f"Base: {metrics.get('base_win_rate', 0):.1%}  "
          f"Tie: {metrics.get('tie_rate', 0):.1%}")
    print(f"  Evaluated on {metrics.get('n_evaluated', 0)} prompts.")
    print("=" * 62 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

async def _main(args: argparse.Namespace) -> None:
    results = await evaluate(args)
    metrics = _aggregate(results)
    _print_summary(metrics)
    log_to_mlflow(results, metrics, args)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="LLM-as-judge eval: base model vs DPO fine-tuned interviewer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Models under evaluation
    p.add_argument("--base-url",    default=DEFAULT_BASE_URL,
                   help="OpenAI-compatible endpoint for the base model",    dest="base_url")
    p.add_argument("--base-model",  default=DEFAULT_BASE_MODEL,
                   help="Model name at --base-url",                         dest="base_model")
    p.add_argument("--tuned-url",   default=None,
                   help="Endpoint for the fine-tuned model (default: same as --base-url)",
                   dest="tuned_url")
    p.add_argument("--tuned-model", default="sdi-interviewer",
                   help="Model name for the DPO fine-tuned model",          dest="tuned_model")
    # Judge
    p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                   help="OpenAI model used as judge (must be at api.openai.com)",
                   dest="judge_model")
    # Dataset & scope
    p.add_argument("--dataset", type=Path, default=DATA_PATH,
                   help="Path to dpo_dataset.jsonl")
    p.add_argument("--n-eval",  type=int, default=10,
                   help="Number of examples to evaluate (taken from the end of the dataset)",
                   dest="n_eval")
    # MLflow
    p.add_argument("--run-id",  default=None,
                   help="Attach results to an existing MLflow run ID (from train_dpo.py)",
                   dest="run_id")
    p.add_argument("--mlflow-tracking-uri", default="./mlruns", dest="mlflow_uri",
                   help="MLflow tracking server URI")
    # Auth
    p.add_argument("--openai-api-key", default=None, dest="openai_api_key",
                   help="OpenAI API key (defaults to OPENAI_API_KEY env var)")
    return p


if __name__ == "__main__":
    import asyncio
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    _args = _build_parser().parse_args()
    if not _args.openai_api_key:
        _args.openai_api_key = os.environ.get("OPENAI_API_KEY", "")

    import mlflow
    mlflow.set_tracking_uri(_args.mlflow_uri)

    asyncio.run(_main(_args))

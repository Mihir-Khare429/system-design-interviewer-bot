"""
Human Likeness Test Suite — System Design Interviewer Bot
=========================================================
Makes live LLM calls and checks that Alex speaks like a real interviewer,
not a chatbot. Each scenario is tested against 9 criteria.

Run via pytest (verbose, with print output):
    python -m pytest tests/test_human_likeness.py -v -s -p no:cov

Run as standalone report (no pytest needed):
    python tests/test_human_likeness.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

# ── env loading for standalone runs ──────────────────────────────────────────
if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass

from openai import AsyncOpenAI, APIConnectionError
from app.config import settings
from app.prompts import (
    DIFFICULTY_PROMPTS,
    PHASE_PROMPTS,
    SYSTEM_DESIGN_INTERVIEWER_PROMPT,
)

pytestmark = pytest.mark.llm

# ── LLM client ────────────────────────────────────────────────────────────────
# Replace Docker-internal hostname so tests also work outside Docker
_base_url = settings.llm_base_url.replace("host.docker.internal", "localhost")
_client = AsyncOpenAI(api_key=settings.openai_api_key or "ollama", base_url=_base_url)
_MODEL = settings.llm_model


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ScenarioResult:
    scenario_name: str
    phase: str
    user_turn: str
    response: str
    latency_ms: int
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def score(self) -> tuple[int, int]:
        passed = sum(1 for c in self.checks if c.passed)
        return passed, len(self.checks)


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _build_messages(
    phase: str,
    history: list[tuple[str, str]],
    difficulty: str = "medium",
    extra_system: str | None = None,
) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_DESIGN_INTERVIEWER_PROMPT}]
    if difficulty in DIFFICULTY_PROMPTS:
        msgs.append({"role": "system", "content": DIFFICULTY_PROMPTS[difficulty]})
    msgs.append({"role": "system", "content": PHASE_PROMPTS[phase]})
    if extra_system:
        msgs.append({"role": "system", "content": extra_system})
    for role, content in history:
        msgs.append({"role": role, "content": content})
    return msgs


async def _call_llm(messages: list[dict]) -> tuple[str, int]:
    t0 = time.monotonic()
    completion = await _client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        max_tokens=80,
        temperature=0.85,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    return completion.choices[0].message.content.strip(), latency_ms


async def _llm_reachable() -> bool:
    try:
        await _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return True
    except Exception:
        return False


# ── Check functions ───────────────────────────────────────────────────────────

_ROBOTIC_OPENERS = [
    "certainly", "of course", "absolutely", "great question",
    "that's a great", "as an ai", "as a language model", "as an interviewer",
    "i'd be happy to", "i'm glad you asked", "excellent question",
    "indeed!", "affirmative", "understood, i will", "noted,",
]

_MARKDOWN_PATTERNS = [
    (r"\*\*[^*]+\*\*", "bold (**text**)"),
    (r"__[^_]+__",     "bold (__text__)"),
    (r"#{1,6}\s\S",    "header (## ...)"),
    (r"`[^`]+`",       "inline code (`...`)"),
    (r"```",           "code block (```)"),
]

_PHASE_META = [
    "in this phase", "during this phase", "as an interviewer",
    "my role is to", "i am designed to", "i will now ask",
    "let's transition", "we are now in the", "moving to",
]

_ENUMERATION_SIGNALS = [
    r"\bfirst(ly)?\b.*\bsecond(ly)?\b",
    r"\b(1|one)\b.*\b(2|two)\b.*\b(3|three)\b",
    r"\bpoint (one|1)\b",
]


def check_no_markdown(r: str) -> CheckResult:
    for pattern, label in _MARKDOWN_PATTERNS:
        if re.search(pattern, r, re.IGNORECASE):
            return CheckResult("no_markdown", False, f"Found {label}")
    return CheckResult("no_markdown", True, "Clean — no markdown symbols")


def check_no_robotic_opener(r: str) -> CheckResult:
    first_50 = r.lower()[:60]
    for phrase in _ROBOTIC_OPENERS:
        if first_50.startswith(phrase) or f" {phrase}" in first_50:
            return CheckResult("no_robotic_opener", False, f"Starts with robotic phrase: '{phrase}'")
    return CheckResult("no_robotic_opener", True, "Natural opening — no canned phrases")


def check_length(r: str) -> CheckResult:
    words = len(r.split())
    if words < 8:
        return CheckResult("length_8_to_100", False, f"Too short — {words} words (min 8)")
    if words > 100:
        return CheckResult("length_8_to_100", False, f"Too long — {words} words (max 100)")
    return CheckResult("length_8_to_100", True, f"{words} words — appropriate length")


def check_ends_with_question(r: str) -> CheckResult:
    stripped = r.rstrip()
    if stripped.endswith("?"):
        return CheckResult("ends_with_question", True, "Response ends with a question mark")
    return CheckResult("ends_with_question", False, "Does not end with a question")


def check_question_count(r: str) -> CheckResult:
    count = r.count("?")
    if count == 0:
        return CheckResult("one_or_two_questions", False, "No question asked (Alex should always ask one)")
    if count > 2:
        return CheckResult("one_or_two_questions", False, f"{count} question marks — too many questions at once")
    return CheckResult("one_or_two_questions", True, f"{count} question(s) — appropriate")


def check_no_bullet_list(r: str) -> CheckResult:
    for line in r.split("\n"):
        stripped = line.strip()
        if re.match(r"^[-*•]\s", stripped) or re.match(r"^\d+[.)]\s", stripped):
            return CheckResult("no_bullet_list", False, f"List item detected: '{stripped[:50]}'")
    return CheckResult("no_bullet_list", True, "No bullet or numbered lists")


def check_no_phase_meta(r: str) -> CheckResult:
    lower = r.lower()
    for phrase in _PHASE_META:
        if phrase in lower:
            return CheckResult("no_phase_meta", False, f"Meta-commentary: '{phrase}'")
    return CheckResult("no_phase_meta", True, "No phase meta-commentary")


def check_no_enumeration(r: str) -> CheckResult:
    lower = r.lower()
    for pattern in _ENUMERATION_SIGNALS:
        if re.search(pattern, lower, re.IGNORECASE | re.DOTALL):
            return CheckResult("no_enumeration", False, "Structured enumeration (First…Second…) detected")
    return CheckResult("no_enumeration", True, "No rigid enumeration structure")


def check_no_all_caps_words(r: str) -> CheckResult:
    # Allow short acronyms (DB, API, URL) but not long ALL-CAPS words
    caps_words = [w for w in r.split() if w.isupper() and len(w) > 4 and w.isalpha()]
    if caps_words:
        return CheckResult("no_all_caps", False, f"ALL-CAPS words: {caps_words[:3]}")
    return CheckResult("no_all_caps", True, "No inappropriate ALL-CAPS shouting")


ALL_CHECKS: list[Callable[[str], CheckResult]] = [
    check_no_markdown,
    check_no_robotic_opener,
    check_length,
    check_ends_with_question,
    check_question_count,
    check_no_bullet_list,
    check_no_phase_meta,
    check_no_enumeration,
    check_no_all_caps_words,
]


def run_checks(response: str) -> list[CheckResult]:
    return [fn(response) for fn in ALL_CHECKS]


# ── Scenarios ─────────────────────────────────────────────────────────────────

ALEX_OPENING = (
    "Hey — thanks for coming in today. I'm Alex, Senior Staff Engineer here, "
    "and I'll be running your system design interview. "
    "How are you doing — feeling ready for this?"
)

SCENARIOS: list[tuple[str, str, str, list[tuple[str, str]], str | None]] = [
    # (name, phase, difficulty, history, extra_system)
    (
        "INTRO — Warmup (first user reply)",
        "INTRO", "medium",
        [
            ("assistant", ALEX_OPENING),
            ("user", "I'm doing well, thanks! Yeah, feeling ready. Let's get into it."),
        ],
        None,
    ),
    (
        "INTRO — Background question (user shares their role)",
        "INTRO", "medium",
        [
            ("assistant", ALEX_OPENING),
            ("user", "I'm doing well, thanks!"),
            ("assistant", "Good to hear. So where are you working these days, and how long have you been building software?"),
            ("user", "I'm a senior backend engineer at a fintech startup. About five years total, mostly Go and Python services."),
        ],
        None,
    ),
    (
        "CONSTRAINTS — User asks about scale",
        "CONSTRAINTS", "hard",
        [
            ("assistant", "Alright, let me give you today's question. Design a URL shortening service — something like bit.ly. Take a minute — ask me anything before you start designing."),
            ("user", "Okay. How many URLs are we expecting to store, and what's the read-to-write ratio?"),
        ],
        "Full problem: Design a URL shortener that handles 100M URLs and 10B redirects per month.",
    ),
    (
        "CONSTRAINTS — User fishes for design hints (should be deflected)",
        "CONSTRAINTS", "medium",
        [
            ("assistant", "Alright — design a real-time messaging app. Ask me anything first."),
            ("user", "What database should I use? Would something like Cassandra work for this?"),
        ],
        "Full problem: Design a real-time chat system like WhatsApp, 500M DAU.",
    ),
    (
        "DESIGN — User describes their high-level architecture",
        "DESIGN", "hard",
        [
            ("assistant", "Alright, walk me through your high-level design."),
            ("user", "So I'd have the client hit a load balancer, behind that a fleet of stateless API servers, then Postgres as the primary store. I'd put Redis in front of Postgres for reads."),
        ],
        None,
    ),
    (
        "DEEP_DIVE — User explains caching strategy (should be challenged)",
        "DEEP_DIVE", "staff",
        [
            ("assistant", "Let's stress-test some of the decisions you made. Your caching layer — walk me through it."),
            ("user", "I'd use Redis with a write-through cache. Every write hits both Redis and Postgres simultaneously. Cache TTL of 24 hours."),
        ],
        None,
    ),
]


# ── Core runner ───────────────────────────────────────────────────────────────

async def run_scenario(
    name: str,
    phase: str,
    difficulty: str,
    history: list[tuple[str, str]],
    extra_system: str | None,
) -> ScenarioResult:
    msgs = _build_messages(phase, history, difficulty=difficulty, extra_system=extra_system)
    response, latency_ms = await _call_llm(msgs)
    checks = run_checks(response)
    return ScenarioResult(
        scenario_name=name,
        phase=phase,
        user_turn=history[-1][1],
        response=response,
        latency_ms=latency_ms,
        checks=checks,
    )


# ── Report printer ────────────────────────────────────────────────────────────

PASS = "✅"
FAIL = "❌"
WIDTH = 72


def _bar(char: str = "─", width: int = WIDTH) -> str:
    return char * width


def _header(title: str) -> str:
    pad = max(0, WIDTH - len(title) - 2)
    left = pad // 2
    right = pad - left
    return f"{'═' * left} {title} {'═' * right}"


def print_report(results: list[ScenarioResult]) -> None:
    print()
    print(_header("HUMAN LIKENESS REPORT — Alex Interviewer"))
    print(f"  Model : {_MODEL}")
    print(f"  Checks: {len(ALL_CHECKS)} per scenario  ·  Scenarios: {len(results)}")
    print(_bar("═"))

    total_checks = 0
    total_passed = 0

    for i, r in enumerate(results, 1):
        passed, total = r.score
        total_checks += total
        total_passed += passed
        pct = int(100 * passed / total) if total else 0
        grade = "PASS" if pct == 100 else ("WARN" if pct >= 70 else "FAIL")
        grade_icon = "✅" if grade == "PASS" else ("⚠️ " if grade == "WARN" else "❌")

        print()
        print(f"  {grade_icon} Scenario {i}/{len(results)} — {r.phase}  [{passed}/{total} checks · {r.latency_ms}ms]")
        print(f"  {r.scenario_name}")
        print(_bar("·"))

        # user turn
        user_preview = r.user_turn[:90] + ("..." if len(r.user_turn) > 90 else "")
        print(f"  USER : {user_preview}")

        # response (wrapped)
        resp_words = r.response.split()
        lines: list[str] = []
        current = "  ALEX : "
        for word in resp_words:
            if len(current) + len(word) + 1 > WIDTH:
                lines.append(current)
                current = "         " + word + " "
            else:
                current += word + " "
        if current.strip():
            lines.append(current.rstrip())
        for line in lines:
            print(line)

        print()
        for check in r.checks:
            icon = PASS if check.passed else FAIL
            name_padded = check.name.ljust(24)
            print(f"    {icon}  {name_padded}  {check.detail}")

        print(_bar("─"))

    # Overall summary
    overall_pct = int(100 * total_passed / total_checks) if total_checks else 0
    overall_icon = "✅" if overall_pct >= 90 else ("⚠️ " if overall_pct >= 70 else "❌")
    print()
    print(_header("OVERALL SUMMARY"))
    print(f"  Scenarios  : {len(results)}")
    print(f"  Checks run : {total_checks}")
    print(f"  Passed     : {total_passed}")
    print(f"  Failed     : {total_checks - total_passed}")
    print(f"  Score      : {overall_pct}%  {overall_icon}")
    print()

    # Per-check breakdown
    check_names = [fn("|placeholder|").name for fn in ALL_CHECKS]
    print("  Per-check breakdown:")
    for name in check_names:
        wins = sum(1 for r in results for c in r.checks if c.name == name and c.passed)
        total_n = len(results)
        bar_filled = int(10 * wins / total_n) if total_n else 0
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        print(f"    {name:<28}  {bar}  {wins}/{total_n}")

    print()
    print(_bar("═"))
    verdict = (
        "Alex speaks like a real human interviewer."
        if overall_pct >= 90
        else (
            "Alex mostly sounds human but has some rough edges."
            if overall_pct >= 70
            else "Alex sounds too robotic — prompt tuning needed."
        )
    )
    print(f"  Verdict: {verdict}")
    print(_bar("═"))


# ── pytest tests (one per scenario) ──────────────────────────────────────────

@pytest.fixture(scope="module")
async def llm_available():
    reachable = await _llm_reachable()
    if not reachable:
        pytest.skip(f"LLM not reachable at {_base_url} — start Ollama or check .env")


@pytest.fixture(scope="module")
def report_accumulator():
    return []


# Generate one test function per scenario using parametrize
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
async def test_human_likeness(scenario, llm_available, report_accumulator, capsys):
    name, phase, difficulty, history, extra_system = scenario
    result = await run_scenario(name, phase, difficulty, history, extra_system)
    report_accumulator.append(result)

    passed, total = result.score
    failed_checks = [c for c in result.checks if not c.passed]

    # Print inline so -s shows progress
    with capsys.disabled():
        pct = int(100 * passed / total)
        print(f"\n  [{pct}%] {name}")
        preview = result.response[:80] + ("..." if len(result.response) > 80 else "")
        print(f"         Response ({result.latency_ms}ms): \"{preview}\"")
        for c in result.checks:
            icon = "✅" if c.passed else "❌"
            print(f"         {icon} {c.name}: {c.detail}")

    # Hard assertions — each failing check is surfaced as a pytest failure
    assert passed >= 6, (
        f"\n\nScenario: {name}\n"
        f"Response: {result.response}\n\n"
        f"Failed checks ({len(failed_checks)}/{total}):\n"
        + "\n".join(f"  ✗ {c.name}: {c.detail}" for c in failed_checks)
    )


# Print full report at the end of the module
@pytest.fixture(scope="module", autouse=True)
def final_report(report_accumulator):
    yield
    if report_accumulator:
        print_report(report_accumulator)


# ── Standalone entry point ────────────────────────────────────────────────────

async def _run_standalone() -> None:
    print(f"\nConnecting to LLM at {_base_url} (model: {_MODEL})…")
    if not await _llm_reachable():
        print(f"\n❌  Cannot reach LLM at {_base_url}")
        print("   Make sure Ollama is running: ollama serve")
        sys.exit(1)

    results: list[ScenarioResult] = []
    for i, (name, phase, difficulty, history, extra_system) in enumerate(SCENARIOS, 1):
        print(f"  Running scenario {i}/{len(SCENARIOS)}: {name}…", end=" ", flush=True)
        r = await run_scenario(name, phase, difficulty, history, extra_system)
        results.append(r)
        passed, total = r.score
        print(f"[{passed}/{total}]")

    print_report(results)

    # Exit with non-zero if any scenario fails
    overall = sum(1 for r in results for c in r.checks if c.passed)
    total   = sum(len(r.checks) for r in results)
    sys.exit(0 if overall / total >= 0.70 else 1)


if __name__ == "__main__":
    asyncio.run(_run_standalone())

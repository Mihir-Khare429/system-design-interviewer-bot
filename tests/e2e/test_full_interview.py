"""
End-to-end interview test.

Simulates a full interview session through all 4 phases (INTRO → CONSTRAINTS →
DESIGN → DEEP_DIVE) using canned STT / LLM / TTS mocks, then asserts on the
scorecard and writes an HTML + JSON report to reports/.

Phase durations are patched to 1 second so the test completes quickly while
exercising the real time-based transition logic.

Run:
    pytest tests/e2e/test_full_interview.py -v -s
"""

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.e2e.conftest import FAKE_AUDIO_B64, FAKE_AUDIO_BYTES

# ── Phase duration override (patched to 1 s so test runs fast) ────────────────
PATCHED_CONSTRAINTS_S = 1
PATCHED_DESIGN_S = 1

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── WebSocket helper ──────────────────────────────────────────────────────────

def recv(ws, expected_type: str | None = None, skip_types: tuple = (), timeout_msgs: int = 25):
    """
    Receive messages from the WebSocket.

    If *expected_type* is given, keeps receiving and returns the first message
    whose type matches (skipping types in *skip_types*).
    Raises AssertionError after *timeout_msgs* messages without a match.
    """
    for _ in range(timeout_msgs):
        msg = ws.receive_json()
        if msg["type"] in skip_types:
            continue
        if expected_type is None or msg["type"] == expected_type:
            return msg
    raise AssertionError(
        f"Did not receive type={expected_type!r} within {timeout_msgs} messages"
    )


def drain_responses(ws, count: int, skip_types: tuple = ("transcript",)):
    """Collect *count* 'response' messages, discarding *skip_types*."""
    collected = []
    while len(collected) < count:
        msg = ws.receive_json()
        if msg["type"] in skip_types:
            continue
        if msg["type"] == "response":
            collected.append(msg)
    return collected


def send_audio(ws):
    ws.send_json({"type": "audio", "data": FAKE_AUDIO_B64, "mime": "audio/webm"})


# ── Reporter ──────────────────────────────────────────────────────────────────

class InterviewRecorder:
    """Collects transcript events and generates a report at the end."""

    def __init__(self):
        self.started_at = datetime.now(timezone.utc)
        self.events: list[dict] = []
        self._phase = "INTRO"
        self._phase_times: dict[str, float] = {"INTRO": time.monotonic()}

    def log(self, role: str, content: str):
        self.events.append({
            "phase": self._phase,
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    def phase_change(self, new_phase: str):
        now = time.monotonic()
        self._phase = new_phase
        self._phase_times[new_phase] = now
        self.events.append({"phase": new_phase, "role": "system", "content": f"[Phase → {new_phase}]", "ts": datetime.now(timezone.utc).isoformat()})

    def record_msg(self, msg: dict):
        if msg["type"] == "transcript":
            self.log("user", msg["text"])
        elif msg["type"] == "response":
            self.log("assistant", msg.get("text", ""))
        elif msg["type"] == "phase_change":
            self.phase_change(msg["phase"])

    def generate_report(self, scorecard: dict, problem_brief: str) -> dict:
        ended_at = datetime.now(timezone.utc)
        duration_s = (ended_at - self.started_at).total_seconds()

        # Count exchanges per phase
        phase_exchanges: dict[str, int] = {}
        for ev in self.events:
            if ev["role"] == "user":
                phase_exchanges[ev["phase"]] = phase_exchanges.get(ev["phase"], 0) + 1

        return {
            "meta": {
                "run_at": self.started_at.isoformat(),
                "duration_seconds": round(duration_s, 1),
                "problem_brief": problem_brief,
            },
            "phases": {
                phase: {"exchanges": phase_exchanges.get(phase, 0)}
                for phase in ["INTRO", "CONSTRAINTS", "DESIGN", "DEEP_DIVE"]
            },
            "scorecard": scorecard,
            "transcript": self.events,
        }


# ── HTML renderer ─────────────────────────────────────────────────────────────

def _render_html(report: dict) -> str:
    meta = report["meta"]
    sc = report["scorecard"]
    lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>SDI E2E Interview Report</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 20px;background:#0f0f10;color:#e0e0e0}",
        "h1{color:#4ade80}h2{color:#a78bfa;margin-top:2em}",
        ".meta{color:#71717a;font-size:.9em}",
        ".phase{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75em;font-weight:600;margin-right:6px}",
        ".INTRO{background:#312e81;color:#a5b4fc}.CONSTRAINTS{background:#451a03;color:#fdba74}",
        ".DESIGN{background:#0c1a2e;color:#7dd3fc}.DEEP_DIVE{background:#2d0b0b;color:#fca5a5}",
        ".msg{margin:8px 0;padding:10px 14px;border-radius:8px;font-size:.9em;line-height:1.5}",
        ".user{background:#1e1e2e;border-left:3px solid #7dd3fc}",
        ".assistant{background:#141420;border-left:3px solid #4ade80}",
        ".system{background:#18181b;border-left:3px solid #71717a;color:#71717a;font-style:italic}",
        ".scorecard{background:#111827;border:1px solid #374151;border-radius:10px;padding:20px;margin-top:16px}",
        ".grade{font-size:3em;font-weight:bold;color:#4ade80}",
        "</style></head><body>",
        f"<h1>SDI E2E Interview Report</h1>",
        f"<p class='meta'>Run: {meta['run_at']} &nbsp;|&nbsp; Duration: {meta['duration_seconds']}s</p>",
        f"<p class='meta'>Problem: <strong>{meta['problem_brief']}</strong></p>",
        "<h2>Scorecard</h2>",
        "<div class='scorecard'>",
        f"<div class='grade'>{sc.get('grade', '?')}</div>",
        f"<p><strong>Decision:</strong> {sc.get('hire', '—')}</p>",
        f"<p>{sc.get('summary', '')}</p>",
        f"<p><strong>Strengths:</strong> {sc.get('strengths', '—')}</p>",
        f"<p><strong>Gaps:</strong> {sc.get('gaps', '—')}</p>",
        f"<p><strong>Study:</strong> {sc.get('study', '—')}</p>",
        "</div>",
        "<h2>Transcript</h2>",
    ]
    for ev in report["transcript"]:
        role = ev["role"]
        phase_tag = f"<span class='phase {ev['phase']}'>{ev['phase']}</span>" if role != "system" else ""
        lines.append(
            f"<div class='msg {role}'>{phase_tag}{ev['content']}</div>"
        )
    lines += ["</body></html>"]
    return "\n".join(lines)


# ── The test ──────────────────────────────────────────────────────────────────

@pytest.mark.timeout(120)
def test_full_10min_interview(e2e_client, test_token):
    """
    Drives Alex through a complete 10-minute interview:
      INTRO (3 exchanges) → CONSTRAINTS (3 questions) → DESIGN (3 explanations)
      → DEEP_DIVE (2 answers) → scorecard.

    Phase time limits are patched to 1 s so the test runs in < 30 s.
    """
    recorder = InterviewRecorder()
    problem_brief = "(patched — no Recall bot in E2E)"

    ws_url = (
        f"/ws/interview"
        f"?difficulty=medium"
        f"&token={test_token}"
    )

    with (
        patch("app.ui_session.CONSTRAINTS_DURATION_S", PATCHED_CONSTRAINTS_S),
        patch("app.ui_session.DESIGN_DURATION_S", PATCHED_DESIGN_S),
    ):
        with e2e_client.websocket_connect(ws_url) as ws:

            # ── Handshake ─────────────────────────────────────────────────────
            started = recv(ws, "session_started")
            assert started["session_id"]

            # Opening greeting from Alex
            opening = recv(ws, "response")
            recorder.record_msg(opening)
            assert "Alex" in opening["text"]
            print(f"\n[INTRO] Alex: {opening['text'][:80]}...")

            # ── INTRO — 3 candidate turns ─────────────────────────────────────
            for i in range(3):
                send_audio(ws)
                transcript = recv(ws, "transcript")
                recorder.record_msg(transcript)

                response = recv(ws, "response", skip_types=("transcript",))
                recorder.record_msg(response)
                print(f"[INTRO {i+1}/3] User: {transcript['text'][:60]}")
                print(f"[INTRO {i+1}/3] Alex: {response['text'][:60]}...")

            # ── CONSTRAINTS phase transition ──────────────────────────────────
            pc = recv(ws, "phase_change", skip_types=("response",))
            recorder.record_msg(pc)
            assert pc["phase"] == "CONSTRAINTS", f"Expected CONSTRAINTS, got {pc['phase']}"
            problem_brief = pc.get("problem_brief", problem_brief)
            print(f"\n[PHASE → CONSTRAINTS] {problem_brief[:80]}")

            # Two scripted responses from Alex (brief announcement + problem)
            for _ in range(2):
                r = recv(ws, "response")
                recorder.record_msg(r)

            # ── CONSTRAINTS — 3 candidate questions ───────────────────────────
            for i in range(3):
                send_audio(ws)
                transcript = recv(ws, "transcript")
                recorder.record_msg(transcript)
                response = recv(ws, "response", skip_types=("transcript",))
                recorder.record_msg(response)
                print(f"[CONSTRAINTS {i+1}/3] Q: {transcript['text'][:60]}")

            # Wait for CONSTRAINTS timer to expire (1 s + buffer)
            time.sleep(PATCHED_CONSTRAINTS_S + 0.5)

            # Next send triggers CONSTRAINTS → DESIGN
            send_audio(ws)
            recv(ws, "transcript")  # consume transcript

            pc = recv(ws, "phase_change", skip_types=("response",))
            recorder.record_msg(pc)
            assert pc["phase"] == "DESIGN", f"Expected DESIGN, got {pc['phase']}"
            print(f"\n[PHASE → DESIGN]")

            # Alex's design prompt
            r = recv(ws, "response")
            recorder.record_msg(r)

            # ── DESIGN — 3 candidate explanations ────────────────────────────
            for i in range(3):
                send_audio(ws)
                transcript = recv(ws, "transcript")
                recorder.record_msg(transcript)
                response = recv(ws, "response", skip_types=("transcript",))
                recorder.record_msg(response)
                print(f"[DESIGN {i+1}/3]: {transcript['text'][:60]}")

            # Wait for DESIGN timer to expire
            time.sleep(PATCHED_DESIGN_S + 0.5)

            # Next send triggers DESIGN → DEEP_DIVE
            send_audio(ws)
            recv(ws, "transcript")

            pc = recv(ws, "phase_change", skip_types=("response",))
            recorder.record_msg(pc)
            assert pc["phase"] == "DEEP_DIVE", f"Expected DEEP_DIVE, got {pc['phase']}"
            print(f"\n[PHASE → DEEP_DIVE]")

            r = recv(ws, "response")
            recorder.record_msg(r)

            # ── DEEP_DIVE — 2 answers ─────────────────────────────────────────
            for i in range(2):
                send_audio(ws)
                transcript = recv(ws, "transcript")
                recorder.record_msg(transcript)
                response = recv(ws, "response", skip_types=("transcript",))
                recorder.record_msg(response)
                print(f"[DEEP_DIVE {i+1}/2]: {transcript['text'][:60]}")

            # ── End interview → scorecard ─────────────────────────────────────
            print("\n[END] Requesting scorecard...")
            ws.send_json({"type": "end"})

            recv(ws, "scorecard_loading", skip_types=("response", "transcript"))
            sc_msg = recv(ws, "scorecard", skip_types=("response", "transcript", "scorecard_loading"))
            scorecard = sc_msg["data"]
            print(f"[SCORECARD] Grade={scorecard.get('grade')} Hire={scorecard.get('hire')}")

    # ── Assertions ────────────────────────────────────────────────────────────
    assert scorecard.get("grade") not in (None, "", "N/A"), "Scorecard must have a real grade"
    assert scorecard.get("hire") not in (None, "", "N/A"), "Scorecard must have a hire decision"
    assert scorecard.get("summary"), "Scorecard must contain a summary"

    # All 4 phases were visited
    phases_seen = {ev["phase"] for ev in recorder.events}
    for phase in ("INTRO", "CONSTRAINTS", "DESIGN", "DEEP_DIVE"):
        assert phase in phases_seen, f"Phase {phase} never appeared in transcript"

    # ── Report ────────────────────────────────────────────────────────────────
    report = recorder.generate_report(scorecard, problem_brief)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = REPORTS_DIR / f"interview_{stamp}.json"
    html_path = REPORTS_DIR / f"interview_{stamp}.html"

    json_path.write_text(json.dumps(report, indent=2))
    html_path.write_text(_render_html(report))

    print(f"\n✓ Report written:")
    print(f"  JSON → {json_path}")
    print(f"  HTML → {html_path}")

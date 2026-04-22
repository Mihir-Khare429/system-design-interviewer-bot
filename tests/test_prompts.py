"""
Tests for app/prompts.py — content and completeness checks.
"""

import pytest
from app.prompts import SCREENSHOT_ANALYSIS_PROMPT, SYSTEM_DESIGN_INTERVIEWER_PROMPT


class TestSystemDesignInterviewerPrompt:
    def test_prompt_is_non_empty_string(self):
        assert isinstance(SYSTEM_DESIGN_INTERVIEWER_PROMPT, str)
        assert len(SYSTEM_DESIGN_INTERVIEWER_PROMPT.strip()) > 100

    def test_prompt_instructs_adversarial_behavior(self):
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "adversarial" in lower or "challenge" in lower or "probe" in lower

    def test_prompt_includes_response_length_constraint(self):
        """The prompt should instruct the model to keep responses short."""
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "sentence" in lower or "short" in lower or "brief" in lower

    def test_prompt_covers_scalability_probing(self):
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "scal" in lower  # scaling / scalability

    def test_prompt_covers_single_points_of_failure(self):
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "failure" in lower or "fault" in lower or "sla" in lower

    def test_prompt_covers_database_topics(self):
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "database" in lower or "db" in lower or "shard" in lower

    def test_prompt_has_opening_instruction(self):
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "opening" in lower or "introduc" in lower or "start" in lower

    def test_prompt_mentions_whiteboard_analysis(self):
        lower = SYSTEM_DESIGN_INTERVIEWER_PROMPT.lower()
        assert "whiteboard" in lower or "diagram" in lower


class TestScreenshotAnalysisPrompt:
    def test_prompt_is_non_empty_string(self):
        assert isinstance(SCREENSHOT_ANALYSIS_PROMPT, str)
        assert len(SCREENSHOT_ANALYSIS_PROMPT.strip()) > 20

    def test_prompt_focuses_on_single_issue(self):
        lower = SCREENSHOT_ANALYSIS_PROMPT.lower()
        assert "one" in lower or "single" in lower

    def test_prompt_requests_targeted_question(self):
        lower = SCREENSHOT_ANALYSIS_PROMPT.lower()
        assert "question" in lower

    def test_prompts_are_distinct(self):
        assert SYSTEM_DESIGN_INTERVIEWER_PROMPT != SCREENSHOT_ANALYSIS_PROMPT

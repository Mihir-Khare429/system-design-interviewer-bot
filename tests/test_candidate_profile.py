"""Tests for candidate profile merge and prompt helpers."""

import json

from app.candidate_profile import (
    _scorecard_list,
    build_candidate_profile_prompt,
    merge_profile_items,
    serialize_candidate_profile,
)
from app.models import CandidateProfile


class TestScorecardList:
    def test_accepts_arrays(self):
        assert _scorecard_list(["Cost estimation", "Failure handling"]) == [
            "Cost estimation",
            "Failure handling",
        ]

    def test_splits_legacy_comma_strings(self):
        assert _scorecard_list("Cost estimation, CDN strategy underspecified") == [
            "Cost estimation",
            "CDN strategy underspecified",
        ]

    def test_accepts_dict_labels(self):
        assert _scorecard_list({"label": "Capacity planning"}) == ["Capacity planning"]


class TestMergeProfileItems:
    def test_increments_existing_item_count(self):
        existing = [
            {
                "label": "Cost estimation",
                "count": 1,
                "first_seen_at": "2026-06-01T00:00:00+00:00",
                "last_seen_at": "2026-06-01T00:00:00+00:00",
                "last_interview_run_id": 1,
            }
        ]
        merged = merge_profile_items(
            json.dumps(existing),
            ["Cost estimation"],
            interview_run_id=2,
            seen_at="2026-06-04T00:00:00+00:00",
        )
        assert merged[0]["label"] == "Cost estimation"
        assert merged[0]["count"] == 2
        assert merged[0]["last_interview_run_id"] == 2

    def test_sorts_persistent_items_first(self):
        merged = merge_profile_items(
            [],
            ["Cost estimation", "Replication lag", "Cost estimation"],
            seen_at="2026-06-04T00:00:00+00:00",
        )
        assert merged[0]["label"] == "Cost estimation"
        assert merged[0]["count"] == 2


class TestCandidateProfilePrompt:
    def test_empty_profile_returns_empty_prompt(self):
        profile = CandidateProfile(user_id=1)
        assert build_candidate_profile_prompt(profile) == ""

    def test_prompt_mentions_targeted_weaknesses(self):
        profile = CandidateProfile(
            user_id=1,
            interview_count=2,
            strengths_json=json.dumps([{"label": "Failure handling", "count": 1}]),
            weaknesses_json=json.dumps([{"label": "Cost estimation", "count": 2}]),
            study_plan_json=json.dumps([{"label": "Back-of-envelope math", "count": 1}]),
        )
        prompt = build_candidate_profile_prompt(profile)
        assert "Cost estimation (seen 2x)" in prompt
        assert "Frame follow-up questions" in prompt

    def test_serialize_empty_profile(self):
        data = serialize_candidate_profile(None, user_id=42)
        assert data["user_id"] == 42
        assert data["weaknesses"] == []
        assert data["interview_count"] == 0

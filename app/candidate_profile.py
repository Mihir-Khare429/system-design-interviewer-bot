"""Candidate learning profile helpers.

The profile is intentionally user-level, not session-level: every completed
scorecard contributes evidence that future interviews can use for targeted
practice.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CandidateProfile

PROFILE_ITEM_LIMIT = 20
PROMPT_WEAKNESS_LIMIT = 3
PROMPT_STRENGTH_LIMIT = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_label(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:220]


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _scorecard_list(value: object) -> list[str]:
    """Coerce scorecard fields into compact labels.

    Scorecards in this app usually return arrays, but older/e2e fixtures may
    return comma-separated strings. This keeps both forms useful.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        value = value.get("label") or value.get("topic") or value.get("title") or value.get("name")
    if isinstance(value, (list, tuple, set)):
        labels: list[str] = []
        for item in value:
            labels.extend(_scorecard_list(item))
        return labels
    if not isinstance(value, str):
        label = _clean_label(value)
        return [label] if label else []

    raw = value.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if parsed is not None:
            return _scorecard_list(parsed)

    pieces = re.split(r"\n+|;|,(?=\s*[A-Z0-9a-z])", raw)
    labels = [_clean_label(piece.strip(" -•\t")) for piece in pieces]
    return [label for label in labels if label]


def _coerce_existing_items(raw: object) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    if not isinstance(raw, list):
        return []

    items: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            label = _clean_label(item.get("label") or item.get("topic") or item.get("title"))
            if not label:
                continue
            items.append({
                "label": label,
                "count": max(0, int(item.get("count") or 0)),
                "first_seen_at": item.get("first_seen_at"),
                "last_seen_at": item.get("last_seen_at"),
                "last_interview_run_id": item.get("last_interview_run_id"),
            })
        else:
            label = _clean_label(item)
            if label:
                items.append({
                    "label": label,
                    "count": 1,
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "last_interview_run_id": None,
                })
    return items


def merge_profile_items(
    existing: object,
    incoming: Iterable[str],
    *,
    interview_run_id: Optional[int] = None,
    seen_at: Optional[str] = None,
) -> list[dict]:
    seen_at = seen_at or _now_iso()
    by_key: dict[str, dict] = {}

    for item in _coerce_existing_items(existing):
        key = _canonical(item["label"])
        if key and key not in by_key:
            by_key[key] = item

    for label in incoming:
        label = _clean_label(label)
        key = _canonical(label)
        if not key:
            continue

        item = by_key.get(key)
        if item is None:
            by_key[key] = {
                "label": label,
                "count": 1,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "last_interview_run_id": interview_run_id,
            }
        else:
            item["count"] = int(item.get("count") or 0) + 1
            item["last_seen_at"] = seen_at
            item["last_interview_run_id"] = interview_run_id
            if not item.get("first_seen_at"):
                item["first_seen_at"] = seen_at

    return sorted(
        by_key.values(),
        key=lambda item: (int(item.get("count") or 0), str(item.get("last_seen_at") or "")),
        reverse=True,
    )[:PROFILE_ITEM_LIMIT]


def replace_profile_items(existing: object, labels: Iterable[str], *, seen_at: Optional[str] = None) -> list[dict]:
    seen_at = seen_at or _now_iso()
    existing_by_key = {
        _canonical(item["label"]): item
        for item in _coerce_existing_items(existing)
        if _canonical(item["label"])
    }
    replacement: list[dict] = []
    used: set[str] = set()

    for label in labels:
        label = _clean_label(label)
        key = _canonical(label)
        if not key or key in used:
            continue
        used.add(key)
        item = existing_by_key.get(key, {})
        replacement.append({
            "label": label,
            "count": max(1, int(item.get("count") or 1)),
            "first_seen_at": item.get("first_seen_at") or seen_at,
            "last_seen_at": item.get("last_seen_at") or seen_at,
            "last_interview_run_id": item.get("last_interview_run_id"),
        })

    return replacement[:PROFILE_ITEM_LIMIT]


async def get_or_create_candidate_profile(db: AsyncSession, user_id: int) -> CandidateProfile:
    profile = (
        await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is not None:
        return profile

    profile = CandidateProfile(user_id=user_id)
    db.add(profile)
    await db.flush()
    return profile


async def update_candidate_profile_from_scorecard(
    db: AsyncSession,
    *,
    user_id: int,
    scorecard: dict,
    interview_run_id: Optional[int] = None,
) -> CandidateProfile:
    profile = await get_or_create_candidate_profile(db, user_id)
    seen_at = _now_iso()

    strengths = _scorecard_list(scorecard.get("strengths"))
    weaknesses = _scorecard_list(scorecard.get("gaps") or scorecard.get("weaknesses"))
    study_plan = _scorecard_list(scorecard.get("study") or scorecard.get("study_plan"))

    profile.strengths_json = json.dumps(
        merge_profile_items(profile.strengths_json, strengths, interview_run_id=interview_run_id, seen_at=seen_at)
    )
    profile.weaknesses_json = json.dumps(
        merge_profile_items(profile.weaknesses_json, weaknesses, interview_run_id=interview_run_id, seen_at=seen_at)
    )
    profile.study_plan_json = json.dumps(
        merge_profile_items(profile.study_plan_json, study_plan, interview_run_id=interview_run_id, seen_at=seen_at)
    )
    profile.summary = _clean_label(scorecard.get("summary")) or profile.summary
    profile.latest_grade = _clean_label(scorecard.get("grade")) or profile.latest_grade
    profile.latest_hire = _clean_label(scorecard.get("hire")) or profile.latest_hire
    profile.interview_count = int(profile.interview_count or 0) + 1
    return profile


def serialize_candidate_profile(profile: Optional[CandidateProfile], *, user_id: Optional[int] = None) -> dict:
    if profile is None:
        return {
            "user_id": user_id,
            "summary": None,
            "strengths": [],
            "weaknesses": [],
            "study_plan": [],
            "latest_grade": None,
            "latest_hire": None,
            "interview_count": 0,
            "updated_at": None,
        }
    return {
        "user_id": profile.user_id,
        "summary": profile.summary,
        "strengths": profile.strengths,
        "weaknesses": profile.weaknesses,
        "study_plan": profile.study_plan,
        "latest_grade": profile.latest_grade,
        "latest_hire": profile.latest_hire,
        "interview_count": profile.interview_count,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def build_candidate_profile_prompt(profile: Optional[CandidateProfile]) -> str:
    if profile is None or (not profile.weaknesses and not profile.strengths):
        return ""

    weaknesses = profile.weaknesses[:PROMPT_WEAKNESS_LIMIT]
    strengths = profile.strengths[:PROMPT_STRENGTH_LIMIT]
    study_plan = profile.study_plan[:PROMPT_WEAKNESS_LIMIT]

    weakness_text = ", ".join(
        f"{item['label']} (seen {int(item.get('count') or 0)}x)" for item in weaknesses
    ) or "none yet"
    strength_text = ", ".join(item["label"] for item in strengths) or "none yet"
    study_text = ", ".join(item["label"] for item in study_plan) or "none yet"

    return (
        "PERSISTENT CANDIDATE PROFILE:\n"
        f"- Accumulated completed interviews: {int(profile.interview_count or 0)}\n"
        f"- Strengths to acknowledge when relevant: {strength_text}\n"
        f"- Weaknesses to explicitly target: {weakness_text}\n"
        f"- Suggested study areas: {study_text}\n"
        "Use this memory in the current interview. Explicitly surface one targeted weakness naturally, "
        "for example by saying you're going to revisit that area today. Frame follow-up questions around "
        "the weak concepts in a new subproblem instead of repeating the exact prior scenario. Still ask "
        "one question at a time and keep the interview realistic."
    )

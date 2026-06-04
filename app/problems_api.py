"""REST endpoints for the problem library and per-user interview history."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_admin, get_current_user
from app.candidate_profile import (
    get_or_create_candidate_profile,
    replace_profile_items,
    serialize_candidate_profile,
)
from app.database import get_db
from app.models import CandidateProfile, InterviewRun, Problem, User
from app.quota import quota_status

router = APIRouter(prefix="/api", tags=["library"])


class CandidateProfileUpdate(BaseModel):
    summary: Optional[str] = None
    strengths: Optional[list[str]] = None
    weaknesses: Optional[list[str]] = None
    study_plan: Optional[list[str]] = None


@router.get("/problems")
async def list_problems(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Problem)
    if category:
        stmt = stmt.where(Problem.category == category)
    rows = (await db.execute(stmt)).scalars().all()
    items = [p.to_dict() for p in rows]
    if difficulty:
        items = [p for p in items if difficulty in p["difficulty"]]
    if search:
        q = search.lower()
        items = [
            p for p in items
            if q in p["title"].lower() or any(q in t.lower() for t in p["tags"])
        ]
    return {"items": items, "count": len(items)}


@router.get("/problems/{slug}")
async def get_problem(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    row = (await db.execute(select(Problem).where(Problem.slug == slug))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Problem not found")
    return row.to_dict()


@router.get("/interviews")
async def my_interviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            select(InterviewRun)
            .where(InterviewRun.user_id == user.id)
            .order_by(InterviewRun.started_at.desc())
            .limit(50)
        )
    ).scalars().all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "session_id": r.session_id,
            "problem_slug": r.problem_slug,
            "difficulty": r.difficulty,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "estimated_cost_usd": r.estimated_cost_usd,
            "scorecard": r.scorecard,
        })

    quota = await quota_status(db, user)
    profile = (
        await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    ).scalar_one_or_none()
    return {
        "items": items,
        "count": len(items),
        "quota": quota,
        "profile": serialize_candidate_profile(profile, user_id=user.id),
    }


@router.get("/interviews/{session_id}")
async def get_interview(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            select(InterviewRun).where(
                InterviewRun.session_id == session_id,
                InterviewRun.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Interview not found")
    return {
        "id": row.id,
        "session_id": row.session_id,
        "problem_slug": row.problem_slug,
        "difficulty": row.difficulty,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "estimated_cost_usd": row.estimated_cost_usd,
        "transcript": row.transcript,
        "scorecard": row.scorecard,
    }


@router.get("/profile")
async def my_candidate_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = (
        await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    ).scalar_one_or_none()
    return serialize_candidate_profile(profile, user_id=user.id)


@router.patch("/admin/users/{user_id}/profile")
async def update_candidate_profile(
    user_id: int,
    req: CandidateProfileUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target_user:
        raise HTTPException(404, "User not found")

    profile = await get_or_create_candidate_profile(db, user_id)
    if req.summary is not None:
        profile.summary = req.summary.strip() or None
    if req.strengths is not None:
        profile.strengths_json = json.dumps(replace_profile_items(profile.strengths_json, req.strengths))
    if req.weaknesses is not None:
        profile.weaknesses_json = json.dumps(replace_profile_items(profile.weaknesses_json, req.weaknesses))
    if req.study_plan is not None:
        profile.study_plan_json = json.dumps(replace_profile_items(profile.study_plan_json, req.study_plan))

    await db.commit()
    await db.refresh(profile)
    return serialize_candidate_profile(profile, user_id=user_id)

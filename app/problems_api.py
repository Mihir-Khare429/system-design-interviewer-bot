"""REST endpoints for the problem library and per-user interview history."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import InterviewRun, Problem, User
from app.quota import quota_status

router = APIRouter(prefix="/api", tags=["library"])


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
    return {"items": items, "count": len(items), "quota": quota}


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

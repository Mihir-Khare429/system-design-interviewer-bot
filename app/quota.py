"""Plan + quota enforcement for interview starts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import InterviewRun, User


def _month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def interviews_used_this_month(db: AsyncSession, user_id: int) -> int:
    start = _month_start_utc()
    result = await db.execute(
        select(func.count(InterviewRun.id)).where(
            InterviewRun.user_id == user_id,
            InterviewRun.started_at >= start,
        )
    )
    return int(result.scalar() or 0)


def monthly_limit(plan: str) -> int:
    return settings.pro_monthly_interviews if plan == "pro" else settings.free_monthly_interviews


async def quota_status(db: AsyncSession, user: User) -> dict:
    used = await interviews_used_this_month(db, user.id)
    limit = monthly_limit(user.plan)
    return {
        "plan": user.plan,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
    }


async def check_can_start_interview(db: AsyncSession, user: User) -> tuple[bool, str]:
    used = await interviews_used_this_month(db, user.id)
    limit = monthly_limit(user.plan)
    if used >= limit:
        return False, (
            f"Monthly limit of {limit} interviews reached on the {user.plan} plan. "
            "Upgrade to Pro for more."
        )
    return True, ""

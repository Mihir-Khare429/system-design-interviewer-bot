"""ORM models for users, subscriptions, interview runs, usage, and problems."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free | pro
    role: Mapped[str] = mapped_column(String(32), default="user")  # user | admin
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interviews: Mapped[list["InterviewRun"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    subscription: Mapped[Optional["Subscription"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    candidate_profile: Mapped[Optional["CandidateProfile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class CandidateProfile(Base):
    """Long-lived, user-level strengths and weaknesses inferred from scorecards."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strengths_json: Mapped[str] = mapped_column(Text, default="[]")
    weaknesses_json: Mapped[str] = mapped_column(Text, default="[]")
    study_plan_json: Mapped[str] = mapped_column(Text, default="[]")
    latest_grade: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    latest_hire: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    interview_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="candidate_profile")

    @staticmethod
    def _loads(raw: Optional[str]) -> list[dict]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []

    @property
    def strengths(self) -> list[dict]:
        return self._loads(self.strengths_json)

    @property
    def weaknesses(self) -> list[dict]:
        return self._loads(self.weaknesses_json)

    @property
    def study_plan(self) -> list[dict]:
        return self._loads(self.study_plan_json)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="subscription")


class InterviewRun(Base):
    __tablename__ = "interview_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    problem_slug: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | completed | abandoned
    transcript_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scorecard_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tts_chars: Mapped[int] = mapped_column(Integer, default=0)
    whisper_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="interviews")

    @property
    def transcript(self) -> list[dict]:
        if not self.transcript_json:
            return []
        try:
            return json.loads(self.transcript_json)
        except Exception:
            return []

    @property
    def scorecard(self) -> Optional[dict]:
        if not self.scorecard_json:
            return None
        try:
            return json.loads(self.scorecard_json)
        except Exception:
            return None


class UsageEvent(Base):
    """Append-only ledger for billing forensics and per-call cost tracking."""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    interview_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("interview_runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # llm | tts | whisper | recall
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[float] = mapped_column(Float, default=0.0)  # seconds for whisper, chars for tts
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64))
    difficulties: Mapped[str] = mapped_column(String(255))  # CSV
    brief: Mapped[str] = mapped_column(Text)
    full: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(512))  # CSV
    companies: Mapped[str] = mapped_column(String(512))  # CSV
    estimated_time: Mapped[str] = mapped_column(String(32), default="45 min")
    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "difficulty": [d for d in self.difficulties.split(",") if d],
            "brief": self.brief,
            "full": self.full,
            "tags": [t for t in self.tags.split(",") if t],
            "companies": [c for c in self.companies.split(",") if c],
            "estimatedTime": self.estimated_time,
            "isPro": self.is_pro,
        }

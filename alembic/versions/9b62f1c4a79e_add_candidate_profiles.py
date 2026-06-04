"""add_candidate_profiles

Revision ID: 9b62f1c4a79e
Revises: d4e4b3d6602f
Create Date: 2026-06-04 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b62f1c4a79e"
down_revision: Union[str, Sequence[str], None] = "d4e4b3d6602f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
    )
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("strengths_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("weaknesses_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("study_plan_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("latest_grade", sa.String(length=16), nullable=True),
        sa.Column("latest_hire", sa.String(length=32), nullable=True),
        sa.Column("interview_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_candidate_profiles_user_id"), "candidate_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_candidate_profiles_user_id"), table_name="candidate_profiles")
    op.drop_table("candidate_profiles")
    op.drop_column("users", "role")

"""Promote (or demote) a user to admin.

Usage:
    python -m scripts.make_admin you@example.com           # promote
    python -m scripts.make_admin you@example.com --revoke  # demote
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import User


async def main(email: str, revoke: bool) -> None:
    await init_db()
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"No user with email {email!r}. Sign up first.")
            return
        user.is_admin = not revoke
        await db.commit()
        action = "demoted to regular user" if revoke else "promoted to admin"
        print(f"{user.email} ({user.id}) {action}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.revoke))

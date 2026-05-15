"""Stripe billing endpoints (test mode).

If `stripe_secret_key` is empty in settings, all endpoints return 503 so the rest
of the app keeps running locally without a real Stripe account.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Subscription, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe not configured (set STRIPE_SECRET_KEY)")
    import stripe  # local import so the app boots without the env var

    stripe.api_key = settings.stripe_secret_key
    return stripe


@router.post("/checkout")
async def create_checkout_session(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not settings.stripe_price_id_pro:
        raise HTTPException(503, "STRIPE_PRICE_ID_PRO not configured")
    stripe = _stripe()

    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
        customer_id = customer["id"]
        user.stripe_customer_id = customer_id
        await db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.stripe_price_id_pro, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id)},
    )
    return {"url": session["url"]}


@router.post("/portal")
async def create_portal_session(user: User = Depends(get_current_user)) -> dict:
    if not user.stripe_customer_id:
        raise HTTPException(400, "No billing account yet — start a checkout first")
    stripe = _stripe()
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=settings.stripe_cancel_url,
    )
    return {"url": portal["url"]}


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "STRIPE_WEBHOOK_SECRET not configured")
    stripe = _stripe()
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.stripe_webhook_secret)
    except Exception as exc:
        raise HTTPException(400, f"Invalid webhook: {exc}")

    etype = event["type"]
    data = event["data"]["object"]
    logger.info("Stripe webhook: %s", etype)

    if etype == "checkout.session.completed":
        user_id = int(data.get("client_reference_id") or data.get("metadata", {}).get("user_id") or 0)
        if user_id:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user:
                user.plan = "pro"
                sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
                if not sub:
                    sub = Subscription(user_id=user.id)
                    db.add(sub)
                sub.stripe_subscription_id = data.get("subscription")
                sub.status = "active"
                await db.commit()

    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = data["id"]
        sub = (await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == sub_id))).scalar_one_or_none()
        if sub:
            sub.status = data.get("status", "inactive")
            cpe = data.get("current_period_end")
            if cpe:
                sub.current_period_end = datetime.fromtimestamp(cpe, tz=timezone.utc)
            user = (await db.execute(select(User).where(User.id == sub.user_id))).scalar_one_or_none()
            if user:
                user.plan = "pro" if sub.status in ("active", "trialing") else "free"
            await db.commit()

    return {"received": True}

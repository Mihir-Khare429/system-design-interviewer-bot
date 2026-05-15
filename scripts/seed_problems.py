"""Seed the problems table from the frontend's static list.

Run after init_db():
    python -m scripts.seed_problems
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Problem


PROBLEMS = [
    {
        "slug": "url-shortener",
        "title": "Design a URL Shortener",
        "category": "Storage",
        "difficulties": "Junior,Mid,Senior,Staff",
        "brief": "Design a service like bit.ly that shortens long URLs.",
        "full": "Design a URL shortening service (bit.ly / TinyURL). 100M new URLs/day, 10:1 read:write, 7-char alphanumeric codes, click analytics, 5-year TTL, 99.9% uptime.",
        "tags": "hashing,caching,NoSQL,SQL,base62",
        "companies": "Google,Amazon,Twitter,Atlassian",
        "estimated_time": "45 min",
        "is_pro": False,
    },
    {
        "slug": "rate-limiter",
        "title": "Design a Rate Limiter",
        "category": "Distributed",
        "difficulties": "Mid,Senior,Staff",
        "brief": "Design a distributed rate limiter for an API gateway.",
        "full": "500K req/s across fleet, <5ms added latency, token-bucket/sliding-window/fixed-window, 50+ edge nodes globally.",
        "tags": "Redis,token bucket,sliding window,distributed",
        "companies": "Stripe,Cloudflare,Twilio,AWS",
        "estimated_time": "45 min",
        "is_pro": False,
    },
    {
        "slug": "news-feed",
        "title": "Design a News Feed",
        "category": "Social",
        "difficulties": "Mid,Senior,Staff",
        "brief": "Design the news feed system for a social network like Facebook or Twitter.",
        "full": "500M DAU, avg 200 follows, 100K posts/s, feed <500ms p95, celebrity fan-out, ML ranking.",
        "tags": "fan-out,Kafka,Redis,CDN,ML ranking",
        "companies": "Meta,Twitter,LinkedIn,TikTok",
        "estimated_time": "60 min",
        "is_pro": False,
    },
    {
        "slug": "chat-system",
        "title": "Design a Chat System",
        "category": "Real-time",
        "difficulties": "Mid,Senior,Staff",
        "brief": "Design a messaging system like WhatsApp or Slack.",
        "full": "1B users, 100M DAU, 4B messages/day, <100ms delivery, 500-member groups, indefinite history, presence, E2E encryption.",
        "tags": "WebSocket,Kafka,Cassandra,presence,encryption",
        "companies": "WhatsApp,Slack,Discord,Telegram",
        "estimated_time": "60 min",
        "is_pro": False,
    },
    {
        "slug": "distributed-cache",
        "title": "Design a Distributed Cache",
        "category": "Distributed",
        "difficulties": "Senior,Staff",
        "brief": "Design a distributed caching layer like Redis Cluster or Memcached.",
        "full": "1M ops/s, p99 <1ms reads, 10TB capacity, TTL/LRU eviction, consistent hashing, RF=2.",
        "tags": "consistent hashing,LRU,replication,eviction",
        "companies": "Amazon,Netflix,Uber,DoorDash",
        "estimated_time": "60 min",
        "is_pro": True,
    },
    {
        "slug": "search-autocomplete",
        "title": "Design Search Autocomplete",
        "category": "Search",
        "difficulties": "Mid,Senior",
        "brief": "Design the typeahead/autocomplete feature for a search engine.",
        "full": "5B searches/day, autocomplete each keystroke, p99 <50ms, top-10 suggestions, personalization, 15-min trending updates.",
        "tags": "trie,Redis,CDN,ranking,personalization",
        "companies": "Google,Bing,Amazon,DoorDash",
        "estimated_time": "45 min",
        "is_pro": False,
    },
    {
        "slug": "payment-system",
        "title": "Design a Payment System",
        "category": "Payments",
        "difficulties": "Senior,Staff",
        "brief": "Design a payment processing system like Stripe or PayPal.",
        "full": "10M tx/day, peak 1K TPS, p99 <3s, exactly-once, PCI-DSS, cards/ACH/wallets, idempotent retries.",
        "tags": "idempotency,saga pattern,distributed transactions,PCI",
        "companies": "Stripe,PayPal,Square,Braintree",
        "estimated_time": "60 min",
        "is_pro": True,
    },
    {
        "slug": "notification-system",
        "title": "Design a Notification System",
        "category": "Messaging",
        "difficulties": "Junior,Mid,Senior",
        "brief": "Design a multi-channel notification system (push, email, SMS).",
        "full": "10M notifications/day, iOS/Android/email/SMS, per-user prefs, retry w/ backoff, per-user rate limits, templates.",
        "tags": "Kafka,APNs,FCM,email,rate limiting",
        "companies": "Airbnb,Uber,Facebook,WhatsApp",
        "estimated_time": "45 min",
        "is_pro": False,
    },
    {
        "slug": "web-crawler",
        "title": "Design a Web Crawler",
        "category": "Distributed",
        "difficulties": "Mid,Senior",
        "brief": "Design a distributed web crawler for a search engine.",
        "full": "1B pages/month, robots.txt politeness, de-dup at 1B URL scale, freshness, distributed.",
        "tags": "Kafka,Bloom filter,distributed queue,DNS,robots.txt",
        "companies": "Google,Amazon,Ahrefs,Common Crawl",
        "estimated_time": "60 min",
        "is_pro": False,
    },
    {
        "slug": "video-streaming",
        "title": "Design a Video Streaming Platform",
        "category": "Storage",
        "difficulties": "Senior,Staff",
        "brief": "Design a video streaming platform like YouTube or Netflix.",
        "full": "500h uploaded/min, 1B views/day, ABR streaming 240p-4K, <2s first frame, global CDN.",
        "tags": "CDN,HLS,transcoding,object storage,adaptive bitrate",
        "companies": "Netflix,YouTube,Twitch,TikTok",
        "estimated_time": "60 min",
        "is_pro": True,
    },
    {
        "slug": "ride-sharing",
        "title": "Design a Ride-Sharing Service",
        "category": "Real-time",
        "difficulties": "Senior,Staff",
        "brief": "Design the backend for a ride-sharing app like Uber or Lyft.",
        "full": "5M rides/day, GPS every 4s, 250K writes/s peak, <10s match latency, surge pricing, live tracking.",
        "tags": "geospatial,WebSocket,Redis,Kafka,quadtree",
        "companies": "Uber,Lyft,DoorDash,Grab",
        "estimated_time": "60 min",
        "is_pro": True,
    },
    {
        "slug": "key-value-store",
        "title": "Design a Key-Value Store",
        "category": "Storage",
        "difficulties": "Senior,Staff",
        "brief": "Design a distributed key-value store like DynamoDB or Cassandra.",
        "full": "1M reads/s, 100K writes/s, p99 <10ms read, 1PB total, RF=3, tunable consistency, no-downtime scaling.",
        "tags": "consistent hashing,LSM tree,quorum,CAP,replication",
        "companies": "Amazon,Google,Meta,Cockroach Labs",
        "estimated_time": "60 min",
        "is_pro": True,
    },
]


async def main() -> None:
    await init_db()
    async with SessionLocal() as db:
        existing_slugs = set(
            (await db.execute(select(Problem.slug))).scalars().all()
        )
        added = 0
        for p in PROBLEMS:
            if p["slug"] in existing_slugs:
                continue
            db.add(Problem(**p))
            added += 1
        await db.commit()
        print(f"Seeded {added} problems ({len(existing_slugs)} already existed).")


if __name__ == "__main__":
    asyncio.run(main())

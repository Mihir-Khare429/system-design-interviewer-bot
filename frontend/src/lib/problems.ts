export type Difficulty = "Junior" | "Mid" | "Senior" | "Staff";
export type Category =
  | "Storage"
  | "Distributed"
  | "Real-time"
  | "Messaging"
  | "Search"
  | "ML"
  | "Payments"
  | "Social";

export interface Problem {
  slug: string;
  title: string;
  category: Category;
  difficulty: Difficulty[];
  brief: string;
  full: string;
  tags: string[];
  estimatedTime: string;
  companies: string[];
}

export const PROBLEMS: Problem[] = [
  {
    slug: "url-shortener",
    title: "Design a URL Shortener",
    category: "Storage",
    difficulty: ["Junior", "Mid", "Senior", "Staff"],
    brief: "Design a service like bit.ly that shortens long URLs.",
    full: `Design a URL shortening service (bit.ly / TinyURL).

Scale targets:
- 100M new URLs shortened per day
- 10:1 read:write ratio (1B reads/day)
- URLs must be unique, 7-character alphanumeric codes
- Shortened URLs must not be predictable / enumerable
- Analytics: click counts per URL, geographic breakdown
- URLs expire after 5 years by default; custom TTLs supported
- 99.9% uptime SLA

Constraints to probe:
- How do you handle hash collisions?
- How do you distribute the counter across nodes?
- Where do you store the mapping — SQL or NoSQL?
- How do you serve 11.5K reads/second at p99 < 10ms?`,
    tags: ["hashing", "caching", "NoSQL", "SQL", "base62"],
    estimatedTime: "45 min",
    companies: ["Google", "Amazon", "Twitter", "Atlassian"],
  },
  {
    slug: "rate-limiter",
    title: "Design a Rate Limiter",
    category: "Distributed",
    difficulty: ["Mid", "Senior", "Staff"],
    brief: "Design a distributed rate limiter for an API gateway.",
    full: `Design a distributed rate limiter that can enforce per-user and per-API-key request quotas.

Scale targets:
- 500K API requests/second across the fleet
- Latency budget: <5ms added per request (p99)
- Quotas: 100 req/s per user, 10,000 req/s per tenant
- Algorithms to support: token bucket, sliding window log, fixed window
- Must work across 50+ edge nodes globally with eventual consistency acceptable
- Quota overrides configurable without service restart

Constraints to probe:
- How do you synchronize counters across edge nodes?
- What's the failure mode when Redis is unavailable?
- How do you prevent a thundering herd at window resets?
- What's your data structure for a sliding window at this throughput?`,
    tags: ["Redis", "token bucket", "sliding window", "distributed"],
    estimatedTime: "45 min",
    companies: ["Stripe", "Cloudflare", "Twilio", "AWS"],
  },
  {
    slug: "news-feed",
    title: "Design a News Feed",
    category: "Social",
    difficulty: ["Mid", "Senior", "Staff"],
    brief: "Design the news feed system for a social network like Facebook or Twitter.",
    full: `Design a social media news feed that shows posts from people a user follows.

Scale targets:
- 500M daily active users
- Average user follows 200 accounts
- 100K posts written per second
- Feed must load in <500ms at p95
- Celebrities: some accounts have 50M+ followers
- Feed is ranked (not chronological) — ML model scores each post
- Users scroll through ~50 posts per session

Constraints to probe:
- Fan-out on write vs fan-out on read — when does each break down?
- How do you handle celebrity accounts with 50M followers?
- Where does the ML ranking model fit in the critical path?
- How do you paginate a ranked feed efficiently?`,
    tags: ["fan-out", "Kafka", "Redis", "CDN", "ML ranking"],
    estimatedTime: "60 min",
    companies: ["Meta", "Twitter", "LinkedIn", "TikTok"],
  },
  {
    slug: "chat-system",
    title: "Design a Chat System",
    category: "Real-time",
    difficulty: ["Mid", "Senior", "Staff"],
    brief: "Design a messaging system like WhatsApp or Slack.",
    full: `Design a real-time chat system supporting 1:1 and group messaging.

Scale targets:
- 1B users, 100M daily active users
- Average 40 messages sent per user per day = 4B messages/day
- Message delivery latency < 100ms (online), best-effort for offline
- Group chats: up to 500 members
- Message history: stored indefinitely, searchable
- Read receipts, typing indicators, online presence
- End-to-end encryption for 1:1 chats

Constraints to probe:
- WebSocket vs long polling vs SSE — when does each break?
- How do you guarantee message ordering in a distributed system?
- How do you handle delivery to an offline user who reconnects?
- How do you fan out a message to 500 group members at 100ms p95?`,
    tags: ["WebSocket", "Kafka", "Cassandra", "presence", "encryption"],
    estimatedTime: "60 min",
    companies: ["WhatsApp", "Slack", "Discord", "Telegram"],
  },
  {
    slug: "distributed-cache",
    title: "Design a Distributed Cache",
    category: "Distributed",
    difficulty: ["Senior", "Staff"],
    brief: "Design a distributed caching layer like Redis Cluster or Memcached.",
    full: `Design a distributed in-memory cache with high availability and horizontal scalability.

Scale targets:
- 1M cache operations per second
- p99 read latency < 1ms
- 10TB total cache capacity across the fleet
- Support for TTL-based eviction, LRU fallback
- Consistent hashing for key distribution
- Replication factor of 2 — can tolerate 1 node failure without data loss

Constraints to probe:
- How does consistent hashing handle node additions/removals?
- What's your eviction policy when a node reaches capacity?
- How do you handle cache stampede (thundering herd on a popular key expiry)?
- How do you ensure the primary and replica stay in sync?`,
    tags: ["consistent hashing", "LRU", "replication", "eviction"],
    estimatedTime: "60 min",
    companies: ["Amazon", "Netflix", "Uber", "DoorDash"],
  },
  {
    slug: "search-autocomplete",
    title: "Design Search Autocomplete",
    category: "Search",
    difficulty: ["Mid", "Senior"],
    brief: "Design the typeahead / autocomplete feature for a search engine.",
    full: `Design a search autocomplete system that suggests completions as a user types.

Scale targets:
- 5B searches per day
- Autocomplete request triggered every keystroke: ~20 keystrokes/search = 100B requests/day
- p99 response time < 50ms
- Top 10 suggestions per prefix
- Personalization: account for user's past searches
- Trending queries surface within 15 minutes of spiking

Constraints to probe:
- How do you store the trie at this scale? Can it fit in memory?
- How do you rank suggestions — frequency alone, or personalization?
- How do you update suggestions when trending queries spike?
- How do you serve from the edge (CDN) vs origin?`,
    tags: ["trie", "Redis", "CDN", "ranking", "personalization"],
    estimatedTime: "45 min",
    companies: ["Google", "Bing", "Amazon", "DoorDash"],
  },
  {
    slug: "payment-system",
    title: "Design a Payment System",
    category: "Payments",
    difficulty: ["Senior", "Staff"],
    brief: "Design a payment processing system like Stripe or PayPal.",
    full: `Design a payment processing platform that handles transactions at scale.

Scale targets:
- 10M transactions per day (~116 TPS average, 1000 TPS peak)
- p99 transaction latency < 3s (external bank calls included)
- Exactly-once processing — no double charges, no missed charges
- PCI-DSS compliance — card data never stored in plain text
- Support for: credit/debit cards, ACH, digital wallets
- Idempotent API — retries must not create duplicate charges
- Reconciliation: daily settlement with acquiring banks

Constraints to probe:
- How do you guarantee exactly-once execution if your service crashes mid-transaction?
- How do you design the idempotency key system?
- What's your rollback strategy if bank API returns success but you crash before writing?
- How do you handle a bank API that's timing out at high load?`,
    tags: ["idempotency", "saga pattern", "distributed transactions", "PCI"],
    estimatedTime: "60 min",
    companies: ["Stripe", "PayPal", "Square", "Braintree"],
  },
  {
    slug: "notification-system",
    title: "Design a Notification System",
    category: "Messaging",
    difficulty: ["Junior", "Mid", "Senior"],
    brief: "Design a multi-channel notification system (push, email, SMS).",
    full: `Design a notification system that delivers messages across push, email, and SMS channels.

Scale targets:
- 10M notifications per day
- Channels: iOS push, Android push, email, SMS
- Delivery latency: push < 1s, email < 5s, SMS < 10s
- Per-user preferences: opt-in/out per channel, quiet hours
- Retry logic: retry failed deliveries up to 3 times with exponential backoff
- Rate limiting: no more than 10 notifications per user per day (configurable)
- Notification templates with variable substitution

Constraints to probe:
- How do you handle the fan-out for a broadcast to 50M users?
- What's your retry strategy when APNs / FCM is down?
- How do you prevent duplicate delivery when retrying?
- How do you prioritize time-sensitive notifications (OTP) over marketing?`,
    tags: ["Kafka", "APNs", "FCM", "email", "rate limiting"],
    estimatedTime: "45 min",
    companies: ["Airbnb", "Uber", "Facebook", "WhatsApp"],
  },
  {
    slug: "web-crawler",
    title: "Design a Web Crawler",
    category: "Distributed",
    difficulty: ["Mid", "Senior"],
    brief: "Design a distributed web crawler for a search engine.",
    full: `Design a scalable web crawler that can crawl billions of web pages.

Scale targets:
- Crawl 1B pages per month (~400 pages/second)
- Politeness: respect robots.txt, crawl-delay headers
- De-duplication: avoid re-crawling the same URL
- Freshness: high-value pages re-crawled every 24h, low-value every 7 days
- Handle dynamic pages (JavaScript-rendered content)
- Distributed across hundreds of worker nodes

Constraints to probe:
- How do you distribute URLs to workers without hot spots?
- How do you detect and handle circular links?
- How do you de-duplicate at 1B URL scale — Bloom filter?
- How do you prioritize pages that change frequently?`,
    tags: ["Kafka", "Bloom filter", "distributed queue", "DNS", "robots.txt"],
    estimatedTime: "60 min",
    companies: ["Google", "Amazon", "Ahrefs", "Common Crawl"],
  },
  {
    slug: "video-streaming",
    title: "Design a Video Streaming Platform",
    category: "Storage",
    difficulty: ["Senior", "Staff"],
    brief: "Design a video streaming platform like YouTube or Netflix.",
    full: `Design a video streaming platform that can upload, transcode, store, and serve videos at global scale.

Scale targets:
- 500 hours of video uploaded per minute
- 1B video views per day
- Adaptive bitrate streaming: 240p, 480p, 720p, 1080p, 4K
- Cold start (first frame) < 2 seconds at p95
- CDN: serve from edge nodes closest to the viewer
- Storage: videos retained indefinitely; thumbnails and metadata also stored

Constraints to probe:
- How does your transcoding pipeline handle a 4-hour 4K video upload?
- How do you chunk and segment video for adaptive bitrate?
- How do you handle a video that suddenly goes viral (10x normal traffic)?
- How do you design the CDN caching strategy — what's your cache key?`,
    tags: ["CDN", "HLS", "transcoding", "object storage", "adaptive bitrate"],
    estimatedTime: "60 min",
    companies: ["Netflix", "YouTube", "Twitch", "TikTok"],
  },
  {
    slug: "ride-sharing",
    title: "Design a Ride-Sharing Service",
    category: "Real-time",
    difficulty: ["Senior", "Staff"],
    brief: "Design the backend for a ride-sharing app like Uber or Lyft.",
    full: `Design a ride-sharing platform that matches riders with nearby drivers in real time.

Scale targets:
- 5M rides per day across 10 major cities
- Location updates: every driver pings GPS every 4 seconds
- 1M active drivers at peak = 250K location writes/second
- Match latency: rider waits < 10s to be matched with a driver
- Surge pricing: pricing updates in near real-time based on supply/demand
- Trip tracking: rider tracks driver position in real time

Constraints to probe:
- How do you store and query driver locations efficiently? (geospatial index)
- How do you implement the matching algorithm at this scale?
- How do you handle the case where the matched driver accepts another ride?
- How does surge pricing work — what's the unit of pricing grid?`,
    tags: ["geospatial", "WebSocket", "Redis", "Kafka", "quadtree"],
    estimatedTime: "60 min",
    companies: ["Uber", "Lyft", "DoorDash", "Grab"],
  },
  {
    slug: "key-value-store",
    title: "Design a Key-Value Store",
    category: "Storage",
    difficulty: ["Senior", "Staff"],
    brief: "Design a distributed key-value store like DynamoDB or Cassandra.",
    full: `Design a distributed key-value store with tunable consistency and high availability.

Scale targets:
- 1M reads/second, 100K writes/second
- p99 read latency < 10ms
- Data size: 1PB total, individual values up to 1MB
- Replication factor: 3 (across 3 availability zones)
- Consistency: tunable — eventual (default) or strong (quorum read/write)
- Horizontal scaling: add nodes with no downtime

Constraints to probe:
- How does consistent hashing distribute keys and handle node failure?
- What's your conflict resolution strategy for concurrent writes to the same key?
- How does your quorum logic change between eventual and strong consistency?
- How do you compact the storage log as it grows? (LSM tree / SSTables)`,
    tags: ["consistent hashing", "LSM tree", "quorum", "CAP", "replication"],
    estimatedTime: "60 min",
    companies: ["Amazon", "Google", "Meta", "Cockroach Labs"],
  },
];

export function getProblemBySlug(slug: string): Problem | undefined {
  return PROBLEMS.find((p) => p.slug === slug);
}

export function getProblems(opts?: {
  category?: Category;
  difficulty?: Difficulty;
  search?: string;
}): Problem[] {
  let results = [...PROBLEMS];
  if (opts?.category) {
    results = results.filter((p) => p.category === opts.category);
  }
  if (opts?.difficulty) {
    results = results.filter((p) => p.difficulty.includes(opts.difficulty!));
  }
  if (opts?.search) {
    const q = opts.search.toLowerCase();
    results = results.filter(
      (p) =>
        p.title.toLowerCase().includes(q) ||
        p.tags.some((t) => t.toLowerCase().includes(q))
    );
  }
  return results;
}

export const DIFFICULTY_COLORS: Record<Difficulty, string> = {
  Junior: "text-green-400 bg-green-400/10 border-green-400/20",
  Mid: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
  Senior: "text-orange-400 bg-orange-400/10 border-orange-400/20",
  Staff: "text-red-400 bg-red-400/10 border-red-400/20",
};

export const CATEGORY_ICONS: Record<Category, string> = {
  Storage: "🗄️",
  Distributed: "🌐",
  "Real-time": "⚡",
  Messaging: "📨",
  Search: "🔍",
  ML: "🧠",
  Payments: "💳",
  Social: "👥",
};

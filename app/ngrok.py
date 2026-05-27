"""
Dynamic ngrok tunnel URL resolver.

ngrok restarts (free tier, container bounces) generate a new public URL.
Querying the local ngrok management API each time avoids stale webhook URLs.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Configurable via env so tests / host-side callers can override.
# Inside Docker the ngrok container is reachable as "ngrok:4040".
_NGROK_API = os.getenv("NGROK_API_URL", "http://ngrok:4040/api/tunnels")

_cached_url: str = ""


async def get_public_url(timeout: float = 3.0) -> str:
    """
    Return the current ngrok HTTPS tunnel URL.

    Falls back to the last successfully resolved URL if the ngrok API is
    temporarily unreachable (e.g. mid-restart).
    """
    global _cached_url
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_NGROK_API)
            resp.raise_for_status()
            for tunnel in resp.json().get("tunnels", []):
                url = tunnel.get("public_url", "")
                if url.startswith("https://"):
                    if url != _cached_url:
                        logger.info("ngrok public URL: %s", url)
                        _cached_url = url
                    return _cached_url
    except Exception as exc:
        logger.warning(
            "ngrok API unavailable (%s) — using cached URL: %s", exc, _cached_url
        )
    return _cached_url

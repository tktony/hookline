"""Rate-limiting utilities for protecting API endpoints from excessive requests."""
from fastapi import HTTPException, Request

from app.config import RATE_LIMIT, RATE_LIMIT_WINDOW_SECONDS
from app.database import redis_client


def get_client_ip(request: Request) -> str:
    """Return the client's IP address from the request."""

    # behind Caddy: real IP is in X-Forwarded-For (first entry)
    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()
    
    return request.client.host


async def rate_limit(request: Request) -> None:
    """Enforce the configured request limit per client IP address."""

    ip = get_client_ip(request)
    key = f"ratelimit:{ip}"

    # Atomically increment the request count for this client.
    count = await redis_client.incr(key)

    # Start the rate-limit window when the first request is recorded.
    if count == 1:
        await redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)

    # Reject requests that exceed the configured limit.
    if count > RATE_LIMIT:
        raise HTTPException(
            status_code=429, detail="rate limit exceeded, try again shortly"
        )

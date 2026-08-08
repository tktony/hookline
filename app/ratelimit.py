from fastapi import HTTPException, Request

from app.database import redis_client

RATE_LIMIT = 10  # requests
WINDOW_SECONDS = 60  # per this window


def get_client_ip(request: Request) -> str:
    # behind Caddy: real IP is in X-Forwarded-For (first entry)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

# 10 per minute per IP
async def rate_limit(request: Request) -> None:
    ip = get_client_ip(request)
    key = f"ratelimit:{ip}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, WINDOW_SECONDS)
    if count > RATE_LIMIT:
        raise HTTPException(
            status_code=429, detail="rate limit exceeded, try again shortly"
        )

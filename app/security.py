"""Authentication dependencies for validating API keys."""

import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ApiKey

bearer_scheme = HTTPBearer()

async def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKey:
    """Validate the bearer token and return the corresponding active API key."""
    
    raw_key = credentials.credentials

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # Only active API keys are eligible for authentication.
    stmt = select(ApiKey).where(
        ApiKey.key_hash == key_hash, 
        ApiKey.is_active.is_(True),
    )

    result = await session.execute(stmt)
    api_key = result.scalar_one_or_none()

    # Reject invalid or inactive credentials with a standard authentication error.
    if api_key is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")

    return api_key
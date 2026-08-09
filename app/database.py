"""Database engines, session factories, and Redis client configuration."""

import os

import redis.asyncio as aioredis
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "+psycopg")
REDIS_URL = os.environ["REDIS_URL"]

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)


# Use the asynchronous engine for FastAPI request handling.
engine = create_async_engine(DATABASE_URL) 
# Provide an async session factory for database dependencies.
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False) 


# Use the synchronous engine for Celery worker tasks.
sync_engine = create_engine(SYNC_DATABASE_URL) 
# Provide a synchronous session factory for worker database operations.
SessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


async def get_session():
    """Provide an asynchronous database session for FastAPI dependencies."""

    async with AsyncSessionLocal() as session:
        yield session 
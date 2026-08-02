import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "+psycopg")

engine = create_async_engine(DATABASE_URL) # For web
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False) # Session Factory

sync_engine = create_engine(SYNC_DATABASE_URL) # For worker
SessionLocal = sessionmaker(sync_engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session 
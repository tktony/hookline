"""Shared pytest fixtures: test database, session, and API client."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import DATABASE_URL
from app.database import Base, get_session
from app.main import app

TEST_DATABASE_URL = DATABASE_URL.rsplit("/", 1)[0] + "/hookline_test"


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a fresh engine + tables per test, yield a session, then tear down."""
    engine_test = create_async_engine(TEST_DATABASE_URL)
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(engine_test, expire_on_commit=False)
    async with TestSessionLocal() as session:
        yield session

    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine_test.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """API client whose DB dependency uses the test session."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

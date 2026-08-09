"""Smoke test: verify the test scaffolding (DB session + API client) works."""


async def test_health_endpoint(client):
    """The health endpoint responds without touching the database."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_db_session_works(db_session):
    """The test database session is usable."""
    from sqlalchemy import text

    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1

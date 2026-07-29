## Session 1

Built: FastAPI skeleton. /health, POST /api/v1/events returns 202 with a fake id. Config loaded from .env via python-dotenv.
Broke: nothing yet - id is invented and thrown away, no db behind it.
Learned: status_code lives on the decorator (FastAPI builds /docs at import time). Fail loud on missing config: os.environ["X"] over .get() so a missing DATABASE_URL crashes at startup, not mid-query.
Next Session: 
    1) Dockerfile for the api 
    2) docker compose with a postgres service 
    3) prove the api container can reach the db (SELECT 1 in the logs)

## Session 2 

Built: Dockerfile (slim, non-root, layer-cached deps) + .dockerignore. docker-compose.yml with api + db + redis on a shared network. First deliberate volume (pgdata) for Postgres - confirmed data survives down/up.
Broke: pip install failed - PowerShell's > wrote requirements.txt as UTF-16 (null bytes). Fixed with Out-File -Encoding utf8.
Learned: -p / ports map laptop:container. uvicorn binds 0.0.0.0 so forwarded traffic is accepted. Compose services resolve each other by service name - 'db' is a real hostname on the network. Software lives in the container, data lives in the volume.
Next Session: 
    1) SQLAlchemy engine + session, app opens a real connection 
    2) first model (events table) 
    3) Alembic init + first migration, watch the table appear in Postgres

## Session 3 
Built: Full DB layer. Three models (Event, ApiKey, DeliveryAttempt) with FKs, indexes, timezone-aware timestamps. Async SQLAlchemy connection layer verified with SELECT 1 at startup. Alembic (async template) wired to models + DATABASE_URL; first migration generated, reviewed, applied - tables live in Postgres. Added volume mount for live code sync. Connected pgAdmin.
Broke: 
    (1) asyncpg missing from image - rebuild fixed. 
    (2) stale image didn't have new models - rebuild. 
    (3) ran alembic on Windows host, couldn't resolve "db" - must run in container. 
    (4) pgAdmin auth failed: another process held host port 5432, moved container to 5433.
Learned: models are class descriptions, migrations turn them into real tables. Alembic runs in the container (db hostname is Docker-network-only). Volume mount is two-way live sync, not a copy. Composite index targets the worker's hot poll query. Every "code changed but container didn't notice" bug = stale image, needs --build.
Next Session: 
    1) wire POST /events to actually write a row (session + get_session dependency) 
    2) GET /events/{id} to read it back 
    3) see a real row appear in pgAdmin
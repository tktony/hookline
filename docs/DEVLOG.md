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

## Session 4
Built: The core loop, end to end. POST /events now persists a real row (async session + get_session dependency) and returns via a Pydantic response model (EventOut). GET /events/{id} reads it back with a 404 path. Celery + Redis wired; sync DB session added alongside the async one for the worker. Wrote the delivery task: loads the event, POSTs to target_url with httpx (10s timeout), logs a DeliveryAttempt (success or exception), bumps attempts_count, marks success on 2xx. First real end-to-end delivery to webhook.site: worker pulled the job, delivered, got 200, DB updated. milestone (core loop live) hit.
Broke: 
    (1) Ruff B008 on Depends in defaults - switched to Annotated[AsyncSession, Depends(...)] 
    (2) editor auto-imported `from sqlalchemy import event`, shadowing the local variable -> deleted 
    (3) had to remember str(event.id) when enqueuing so Celery can JSON-serialize the arg.
Learned: response_model is the serializer AND an output filter - return the ORM object, FastAPI shapes it. Celery task args must be JSON-serializable (pass ids, not objects). attempt_number reads the counter, attempts_count += 1 writes it - read/write pair. Non-2xx should stay pending for retry, not be marked failed.
Next Session: 
    1) retry + exponential backoff (1m/5m/15m capped, max 5) with next_attempt_at 
    2) dead-letter after max_retries 
    3) reschedule failures instead of leaving them pending

## Session 5
Built: The full retry engine, autonomous. deliver_event now has the failure path: on non-2xx/exception, either mark dead (attempts_count >= max_retries) or schedule a retry (exponential backoff into next_attempt_at, status retrying). Wrote poll_retries: queries retrying+due events (uses the composite index), claims them queued (two-loop: commit claim before enqueue), re-enqueues deliver_event. Wired Celery Beat (separate service) to run poll every 60s. Added GET /api/v1/events?status= list endpoint. Full loop verified end to end against httpbin/500: beat -> poll -> re-enqueue -> worker -> re-deliver, attempts climbing, delivery_attempts logging each try, all with no manual action.
Broke/caught: 
    (1) len-1 vs len(BACKOFF_SCHEDULE)-1 index bug. 
    (2) editor was shadowing again earlier - watched imports. 
    (3) found a real design gap: a claimed "queued" event lost before delivery gets orphaned (poll only scans retrying) - documented as a future fix, it's what the demo will prove.
Learned: the ORM object IS the row - changing event.x and committing = UPDATE; session.add = INSERT. DeliveryAttempt is the append-only audit log (the product's actual value); None-pattern encodes "bad response" vs "no response". Beat schedules, worker executes, Redis is the belt between. Claim-before-enqueue needs the commit first to be race-safe.
Next Session: 
    1) deploy walking skeleton to a VPS, Caddy HTTPS, compose on the server 
    2) GitHub Actions deploy on push to main 
    3) run migrations on the server, confirm the live loop works at the domain

## Session 6
Built: Full production deployment. Provisioned a VPS (Ubuntu), hardened it (non-root sudo user, ufw 22/80/443, root SSH disabled). Deployed the whole stack via git clone + docker compose on the server; ran migrations and seeded the placeholder key against a fresh volume with a strong generated password. Bought tryhookline.dev, pointed A records at the server (DNS-only). Added Caddy as reverse proxy - automatic Let's Encrypt HTTPS, obtained a real cert, API no longer exposes 8000. Set up GitHub Actions to auto-deploy on push to main via a dedicated deploy key (SSH-and-pull). Verified end to end: posted a live event over HTTPS, watched it deliver. Live at https://tryhookline.dev.
Broke/caught: 
    (1) password auth failures twice = the "POSTGRES_PASSWORD only applies on fresh volume init" again; fixed with down -v locally, fresh volume on server. 
    (2) nuked local Docker mid-session, rebuilt from repo + .env in four commands. 
    (3) local worker spamming "relation events does not exist" - missing local migration after the volume wipe.
Learned: DNS A record maps name -> IP, registrar/DNS-host/server-host are separate roles. Caddy needs port 80 for the ACME challenge and the HTTP->HTTPS redirect. Firewall protects DB/Redis even with host ports mapped. Two environments now (laptop = dev, server = prod) - commands run wherever the terminal is; always check the prompt. Dedicated revocable deploy key > personal key for automation. .env is a local convenience, not a deploy mechanism - prod secrets come from the server's own .env.
Next session: 
    1) stuck-in-queue fix
    2) SSRF Guard 
    3) Harden delivery path (response body truncation + request timeout)
    4) API Key Auth mechanism

## Session 7
Built: The full security/hardening pass. 
    (1) stuck-in-queued fixed - poll now rescues claims older than a 5-min grace window, stamping claim time in next_attempt_at; retry loop is now crash-safe 
    (2) SSRF guard - resolves target hostname to IP, rejects private/internal ranges, fails closed, marks blocked events dead. 
    (3) Response-body truncation at 10KB and incoming payload cap at 256KB. 
    (4) Confirmed and documented the 10s delivery timeout's purpose. 
    (5) API key auth end to end: app/cli.py mints keys (secrets + sha256 hash, raw key shown once), require_api_key dependency checks the Authorization: Bearer header, POST /events now requires a valid key and stamps the real key id - DEV_API_KEY_ID placeholder deleted. Verified: blocked URLs die, oversized payloads 422, unauthenticated POST rejected, authenticated POST works.
Broke/caught: 
    (1) forgot to try/except socket.gethostbyname - would crash on unresolvable domains; fixed to fail closed. 
    (2) GitHub Actions stopped triggering after a couple runs (idk why) - deployed SSRF manually via SSH.
    (3) payload measures bytes but response truncation measures chars - intentional (precise reject-threshold vs approximate debug snippet, and char-slicing avoids splitting UTF-8).
Learned: check resolved IPs not hostname strings for SSRF (string matching is trivially bypassed). Fail closed on security checks. Fast sha256 is right for high-entropy keys; bcrypt is for low-entropy passwords. Keys shown once because only the hash is stored - unrecoverable by design. Timeout protects the worker pool from hanging targets. The CLI is an operator tool run against a live instance (docker compose exec), not something consumers run - consumers use the key over HTTP.
Next session: 
    1) deploy the auth work to the server (mint a real server-side key via the CLI, retire the placeholder row) 
    2) observability - Prometheus metrics + Grafana dashboard 
    3) Sentry, nightly pg_dump backup, UptimeRobot on /health. (Backlog: per-IP rate limiting, idempotency key.)
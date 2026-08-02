# Decisions

## 202 not 201 for POST /events
Chose: 202 Accepted. Rejected: 201 Created.
Why: the row exists but the delivery hasn't happened. 202 tells the client "accepted, not done" - don't read the response as delivery confirmation.

## Fail loud on missing config
Chose: os.environ["DATABASE_URL"] (crashes at startup if unset). Rejected: .get() (returns None).
Why: a missing db url is fatal either way. Crashing at import shows the cause immediately; None fails later inside a query with a confusing traceback.

## Run the container as a non-root user
Chose: create an unprivileged appuser in the Dockerfile, USER appuser. Rejected: default root.
Why: if the app is compromised, the attacker is confined to a non-root user inside the container instead of root. Costs nothing, standard production hardening.

## Redis is disposable, Postgres is the source of truth
Chose: no volume on Redis; named volume (pgdata) only on Postgres. Rejected: persisting Redis too.
Why: Redis holds the queue, which is transient. All durable state (webhook rows, attempt history) lives in Postgres. If Redis is wiped on restart, the design recovers by re-reading pending work from Postgres - so persisting Redis buys nothing.

## Composite index on Event(status, next_attempt_at)
Chose: a two-column index on status + next_attempt_at. Rejected: no index / separate single-column indexes.
Why: the worker polls "find events WHERE status='retrying' AND next_attempt_at < now()" on a loop. Without an index Postgres scans every row each poll. A composite index on exactly those filter columns keeps that hot query fast as the table grows.

## Kept Python-side UUID generation
Chose: default=uuid.uuid4 (Python generates the id). Rejected: server_default=gen_random_uuid() (Postgres generates it).
Why: POST /events returns the id immediately in its 202 response. Python-side means the id is known before insert, no read-back. DB-side would be a lateral move, not an upgrade, for this access pattern.

## Timezone-aware timestamps everywhere
Chose: DateTime(timezone=True) on created_at, attempted_at, next_attempt_at. Rejected: naive datetimes.
Why: this is a scheduling system - retries fire at next_attempt_at across time. Naive timestamps are a classic source of off-by-an-hour retry bugs. Store aware, always.

## Alembic runs in the container, not on the host
Chose: docker compose run --rm api alembic ... for all migration commands. Rejected: running alembic on Windows directly.
Why: DATABASE_URL uses host "db", which only resolves inside the Docker network. Local alembic can't reach the DB. Running in the container means alembic uses the same connection the app does. Volume mount syncs generated migration files back to disk.

## Postgres host port moved to 5433 (local dev only)
Chose: map host 5433 -> container 5432 for pgAdmin. Rejected: default 5432:5432.
Why: another process on the host already held 5432, so pgAdmin hit the wrong Postgres and auth failed. 5433 sidesteps the clash. Note: the app still connects internally via db:5432 - unaffected. In production the host port mapping is removed entirely; the DB is never exposed to the host.

## Sync worker, async API
Chose: async SQLAlchemy for the API, a separate sync engine/session for the Celery worker (worker task is a plain sync function with httpx.Client)
Why: Celery's async support is awkward and buys nothing at a few hundred deliveries/min. FastAPI gives async for free on the request path where it matters. Two connection styles in one project - async for web, sync for background work - is simpler to reason about and debug than forcing async into Celery.

## Pass ids to tasks, not objects
Chose: enqueue with deliver_event.delay(str(event.id)) - the worker re-loads the event from the id. Rejected: passing the ORM object or a raw UUID.
Why: Celery serializes task arguments to JSON through Redis. ORM objects and UUIDs aren't JSON-serializable. Passing a string id survives the broker boundary; the worker loads a fresh object in its own session. Also avoids stale-object issues across processes.

## Redis carries the job, Postgres carries the data
Chose: Postgres stores the event row (source of truth); Redis only carries a lightweight "deliver event X" message. Rejected: putting delivery state in Redis.
Why: durability lives in Postgres (survives everything); the queue is transient. If Redis is wiped, pending events can be recovered by querying Postgres.

## Happy path first, retry left open
Chose: on 2xx mark success; on non-2xx or exception, log the attempt but leave status untouched (pending). Rejected: marking non-2xx as "failed" immediately.
Why: a 500 or timeout is exactly what should be retried, not given up on. Marking "failed" would kill retryable events. Leaving status pending is the clean seam where backoff/retry logic (next session) plugs in.
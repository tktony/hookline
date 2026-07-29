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
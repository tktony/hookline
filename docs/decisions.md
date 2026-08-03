## Session 1

### 202 not 201 for POST /events
Chose: 202 Accepted. Rejected: 201 Created.
Why: the row exists but the delivery hasn't happened. 202 tells the client "accepted, not done" - don't read the response as delivery confirmation.

### Fail loud on missing config
Chose: os.environ["DATABASE_URL"] (crashes at startup if unset). Rejected: .get() (returns None).
Why: a missing db url is fatal either way. Crashing at import shows the cause immediately; None fails later inside a query with a confusing traceback.



## Session 2

### Run the container as a non-root user
Chose: create an unprivileged appuser in the Dockerfile, USER appuser. Rejected: default root.
Why: if the app is compromised, the attacker is confined to a non-root user inside the container instead of root. Costs nothing, standard production hardening.

### Redis is disposable, Postgres is the source of truth
Chose: no volume on Redis; named volume (pgdata) only on Postgres. Rejected: persisting Redis too.
Why: Redis holds the queue, which is transient. All durable state (webhook rows, attempt history) lives in Postgres. If Redis is wiped on restart, the design recovers by re-reading pending work from Postgres - so persisting Redis buys nothing.



## Session 3

### Composite index on Event(status, next_attempt_at)
Chose: a two-column index on status + next_attempt_at. Rejected: no index / separate single-column indexes.
Why: the worker polls "find events WHERE status='retrying' AND next_attempt_at < now()" on a loop. Without an index Postgres scans every row each poll. A composite index on exactly those filter columns keeps that hot query fast as the table grows.

### Kept Python-side UUID generation
Chose: default=uuid.uuid4 (Python generates the id). Rejected: server_default=gen_random_uuid() (Postgres generates it).
Why: POST /events returns the id immediately in its 202 response. Python-side means the id is known before insert, no read-back. DB-side would be a lateral move, not an upgrade, for this access pattern.

### Timezone-aware timestamps everywhere
Chose: DateTime(timezone=True) on created_at, attempted_at, next_attempt_at. Rejected: naive datetimes.
Why: this is a scheduling system - retries fire at next_attempt_at across time. Naive timestamps are a classic source of off-by-an-hour retry bugs. Store aware, always.

### Alembic runs in the container, not on the host
Chose: docker compose run --rm api alembic ... for all migration commands. Rejected: running alembic on Windows directly.
Why: DATABASE_URL uses host "db", which only resolves inside the Docker network. Local alembic can't reach the DB. Running in the container means alembic uses the same connection the app does. Volume mount syncs generated migration files back to disk.

### Postgres host port moved to 5433 (local dev only)
Chose: map host 5433 -> container 5432 for pgAdmin. Rejected: default 5432:5432.
Why: another process on the host already held 5432, so pgAdmin hit the wrong Postgres and auth failed. 5433 sidesteps the clash. Note: the app still connects internally via db:5432 - unaffected. In production the host port mapping is removed entirely; the DB is never exposed to the host.



## Session 4

### Sync worker, async API
Chose: async SQLAlchemy for the API, a separate sync engine/session for the Celery worker (worker task is a plain sync function with httpx.Client)
Why: Celery's async support is awkward and buys nothing at a few hundred deliveries/min. FastAPI gives async for free on the request path where it matters. Two connection styles in one project - async for web, sync for background work - is simpler to reason about and debug than forcing async into Celery.

### Pass ids to tasks, not objects
Chose: enqueue with deliver_event.delay(str(event.id)) - the worker re-loads the event from the id. Rejected: passing the ORM object or a raw UUID.
Why: Celery serializes task arguments to JSON through Redis. ORM objects and UUIDs aren't JSON-serializable. Passing a string id survives the broker boundary; the worker loads a fresh object in its own session. Also avoids stale-object issues across processes.

### Redis carries the job, Postgres carries the data
Chose: Postgres stores the event row (source of truth); Redis only carries a lightweight "deliver event X" message. Rejected: putting delivery state in Redis.
Why: durability lives in Postgres (survives everything); the queue is transient. If Redis is wiped, pending events can be recovered by querying Postgres.

### Happy path first, retry left open
Chose: on 2xx mark success; on non-2xx or exception, log the attempt but leave status untouched (pending). Rejected: marking non-2xx as "failed" immediately.
Why: a 500 or timeout is exactly what should be retried, not given up on. Marking "failed" would kill retryable events. Leaving status pending is the clean seam where backoff/retry logic (next session) plugs in.



## Session 5

### Approach B for retries: schedule in Postgres, poll for due work
Chose: store next_attempt_at in Postgres, a periodic poll re-enqueues due events. Rejected: Celery countdown/ETA (Approach A).
Why: with countdown, the retry schedule lives only in Redis - a flush loses every pending retry and the event is orphaned in "retrying" forever. Storing next_attempt_at in Postgres makes the schedule durable; a poll recovers everything after a Redis/worker outage. This is what backs the "nothing is lost" claim, and it's why the composite index on (status, next_attempt_at) exists.

### Exponential backoff, capped
Chose: BACKOFF_SCHEDULE = [60, 300, 900, 1800, 3600]s, index = min(attempts_count - 1, len - 1), max_retries then dead. Rejected: fixed interval; uncapped growth.
Why: escalating delays give a failing target room to recover without hammering it; the cap stops the delay growing unboundedly; a hard max_retries stops infinite retries and moves the event to a terminal "dead" state with full attempt history preserved.

### Claim-before-enqueue with a distinct status, two-loop commit
Chose: poll flips due events retrying -> queued, commits, THEN enqueues (two loops). Rejected: single loop enqueuing before commit; reusing "pending" for the claimed state.
Why (two loops): committing the claim before enqueuing guarantees a delivery can never start on an event whose claim isn't durable yet - closes the window where a task runs before the status flip is written. Why "queued" not "pending": pending means "new, never attempted"; queued means "claimed retry, in flight". Separating them keeps status unambiguous for debugging and makes lost-claim events findable by status.

### Known gap: lost claims stuck in "queued" (TODO: Fix needed)
If a claimed (queued) event is lost before delivery (Redis down / worker crash), nothing re-picks it up - poll only scans "retrying". Fix planned: poll also rescues queued events older than a grace window. This is exactly what the demo will prove survives. Documented now, implemented later

### GET /events list endpoint (TODO: Add Pagination)
Chose: GET /api/v1/events with optional ?status= filter for inspecting events (e.g. dead). Rejected: per-status endpoints.
Why: one filtered list endpoint is simpler and covers debugging any status. Returns all matches with no limit - pagination is a noted item, fine for the current small dataset. Separate from Prometheus, which tracks aggregate counts, not individual rows.
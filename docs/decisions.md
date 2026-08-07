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

## Session 6

### Deploy target: single VPS + docker compose, not managed/registry-based
Chose: one Server, git clone on the server, docker compose up. Rejected: build-image-in-CI + push-to-registry + pull (Approach B), and managed platforms.
Why: Registry-based CI/CD is the "proper" pattern for teams but adds a registry, image tagging, and more moving parts for zero benefit at this scale. Single-VPS compose does the job. 

### Server hardening before anything runs
Chose: non-root sudo user, ufw allowing only 22/80/443, root SSH login disabled, tested the new user before locking root out. Rejected: running as root, leaving all ports open.
Why: the box is public the moment it exists. Least privilege limits blast radius if compromised; the firewall means DB/Redis are unreachable externally even though compose maps their host ports; testing the new user before disabling root avoids locking myself out.

### Caddy for reverse proxy + automatic HTTPS
Chose: Caddy in front of the API, auto TLS via Let's Encrypt. Rejected: nginx + manual certbot; exposing the API directly on 8000.
Why: Caddy fetches and auto-renews certificates with ~3 lines of config - removes the most error-prone part of production HTTPS (cert renewal). API no longer exposes 8000 to the host; all external traffic enters through Caddy on 443, everything else internal. Port 80 stays open for the ACME challenge and HTTP->HTTPS redirect. Cert volume (caddy_data) persists certs across restarts to avoid Let's Encrypt rate limits.

### Secrets from environment, never in the repo or compose
Chose: POSTGRES_PASSWORD (and REDIS_URL) read via ${VAR} from .env, which is gitignored; server .env has a strong openssl-generated password. Rejected: hardcoding "secret" in docker-compose.yml.
Why: a hardcoded password in a public repo is a real vulnerability. ${VAR}-from-.env keeps the compose file identical across local and prod while the actual secret differs per environment and never enters git. Same variable names, different values.

### Dedicated deploy key for CI/CD, not the personal key
Chose: a separate passphrase-less ed25519 key just for GitHub Actions, public half in the server's authorized_keys, private half in GitHub encrypted secrets. Rejected: reusing my personal SSH key.
Why: least privilege and revocability. If the CI key leaks, remove one line from authorized_keys and rotate - my personal access is untouched. Passphrase-less because Actions can't type one interactively; safe because it's dedicated and revocable.

### Auto-deploy: SSH-and-pull on push to main
Chose: GitHub Actions SSHes into the server and runs git pull + docker compose up -d --build + alembic upgrade head. Rejected: manual SSH deploys; registry-based image delivery.
Why: automates the exact manual steps, so "how does deploy work" has a simple honest answer. Running migrations every deploy is safe (no-op when nothing's pending) and means schema changes ship automatically. Rebuild-every-deploy is slightly slow but simple; optimizing it isn't worth the complexity yet.

## Session 7

### Rescue stuck "queued" events after a 5-minute grace window
Chose: poll also picks up events stuck in "queued" whose claim timestamp is older than 5 minutes. Rejected: only ever scanning "retrying" (leaves lost claims orphaned).
Why: when poll claims a due retry (retrying -> queued) and enqueues it, a worker crash or Redis flush before delivery would strand the event in "queued" forever, since poll only looked at "retrying". Stamping next_attempt_at at claim time lets poll detect stale claims and re-queue them. The grace window is 5 minutes because it must be safely longer than worst-case in-flight time (10s request timeout + up to 60s poll interval) so a legitimately in-progress delivery is never rescued out from under a working worker; 5 min is a comfortable margin over ~70s. This is what backs the "nothing is lost" guarantee 

### SSRF guard: reject targets resolving to internal addresses
Chose: resolve the target hostname to an IP and reject private/loopback/link-local/reserved/multicast ranges before the worker makes the request; fail closed on resolution failure; mark blocked events dead (no retry). Rejected: string-matching hostnames like "localhost".
Why: a public webhook sender is an SSRF machine - an attacker can point it at cloud metadata (169.254.169.254), internal services, or private hosts, and read the response back via the attempt log. Checking the resolved IP (not the string) defeats bypasses like domains that resolve to internal IPs, octal/decimal encodings, etc. Fail closed because a security check must reject on uncertainty. Blocked = dead because the URL will never become safe on retry. Known limitation: DNS rebinding (httpx re-resolves at request time); fully closing it needs pinning the resolved IP into the request - noted as future work.

### sha256 for API keys (not bcrypt)
Chose: store sha256 hashes of API keys. Rejected: bcrypt/argon2.
Why: slow hashes (bcrypt) exist to resist brute-forcing low-entropy human passwords. API keys are already high-entropy random strings (secrets.token_urlsafe(32)) - a 256-bit random space can't be brute-forced regardless of hash speed - so a fast sha256 is appropriate and standard. Keys are shown once because only the hash is stored; the raw key is unrecoverable by design, so a DB breach exposes no usable credentials.

### Auth on POST only, GET endpoints left open
Chose: require an API key on POST /events; leave GET /events and GET /events/{id} open. Rejected: auth on everything.
Why: POST creates work and consumes resources - it's the sensitive operation. Reads of event status are low-risk, and the public demo page polls GET /events/{id} to show live delivery status; requiring a key there would mean embedding a secret in public browser JS. Auth the write, leave reads open

### Bounded I/O in both directions
Chose: reject incoming payloads over 256KB at validation (bytes, exact); truncate stored response bodies at 10,000 chars with a marker. Rejected: unbounded payload/response storage.
Why: prevents resource exhaustion from oversized data either way. Payload cap measures bytes because it's a precise rejection threshold (true storage/bandwidth cost). Response truncation measures characters because it's an approximate debug snippet on a Text column, and slicing a decoded str never splits a multi-byte UTF-8 character (byte-slicing could). Different precision for different jobs.

### 10-second delivery timeout
Chose: httpx timeout=10.0 on delivery requests. Rejected: no timeout.
Why: without a timeout, a target that accepts the connection then hangs would block a worker forever; enough hanging targets exhaust the worker pool and halt all deliveries. The timeout guarantees no single target ties up a worker beyond 10s - the sender's throughput is protected from receiver misbehavior. Failed requests are caught, logged, and retried.
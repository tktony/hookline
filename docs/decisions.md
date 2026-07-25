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
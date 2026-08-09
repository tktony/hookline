"""Application configuration and runtime limits."""

import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

MAX_PAYLOAD_BYTES = 256_000  # Maximum webhook payload size in bytes (256 KB).
RATE_LIMIT = 10  # Maximum requests allowed per client within the rate-limit window.
RATE_LIMIT_WINDOW_SECONDS = 60  # Duration of the rate-limit window in seconds.
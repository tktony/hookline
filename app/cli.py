"""CLI utility for creating and managing Hookline API keys."""

import argparse
import hashlib
import secrets

from app.database import SessionLocal
from app.models import ApiKey


def create_key(label: str):
    """Generate an API key, store its hash, and display the raw key once."""

    # Generate a cryptographically secure API key with a recognizable prefix.
    raw_key = f"hl_live_{secrets.token_urlsafe(32)}"

    # Store only the SHA-256 hash so the raw credential is not persisted.
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    session = SessionLocal()
    try:
        api_key = ApiKey(key_hash=key_hash, label=label)
        session.add(api_key)
        session.commit()
        session.refresh(api_key)

        print(f"Created API key (id={api_key.id}, label={label})")
        print(f"Raw key (save now, shown only once): {raw_key}")

    finally:
        session.close()


# TODO: list-keys, revoke-key functions


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create-key")
    create.add_argument("--label", required=True)

    args = parser.parse_args()

    if args.command == "create-key":
        create_key(args.label)
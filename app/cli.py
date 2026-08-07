import argparse
import hashlib
import secrets

from app.database import SessionLocal
from app.models import ApiKey

"""
    Responsibility: 
        1. Generate a random key
        2. Store it's hash
        3. Print raw key once 
"""

def create_key(label: str):
    raw_key = f"hl_live_{secrets.token_urlsafe(32)}"
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
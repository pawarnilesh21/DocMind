"""Add a private signing key to existing local environment files without printing it."""

import secrets
from pathlib import Path

from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    for name in (".env", ".env.local-review"):
        path = root / name
        if not path.exists():
            continue
        if dotenv_values(path).get("JWT_SECRET_KEY"):
            print(f"{name}: existing JWT key preserved.")
            continue
        with path.open("a", encoding="utf-8") as config:
            config.write(f"\nJWT_SECRET_KEY={secrets.token_hex(32)}\n")
        print(f"{name}: generated a JWT signing key (value hidden).")


if __name__ == "__main__":
    main()

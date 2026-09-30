"""Create the local Docker configuration without printing or overwriting secrets."""

import secrets
from pathlib import Path

from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env.local-review"
    if destination.exists():
        print(".env.local-review already exists; kept the existing configuration.")
        return

    existing = dotenv_values(root / ".env")
    values = {"POSTGRES_PASSWORD": secrets.token_hex(32), "JWT_SECRET_KEY": secrets.token_hex(32)}
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        value = existing.get(name)
        if not value or value.startswith("replace_with_"):
            raise SystemExit(f"Set {name} in .env before preparing the local configuration.")
        if any(character in value for character in "\r\n'\\"):
            raise SystemExit(f"{name} contains unsupported characters; configuration was not written.")
        values[name] = value

    lines = []
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.partition("=")[0]
        lines.append(f"{key}='{values[key]}'" if key in values else line)

    with destination.open("x", encoding="utf-8", newline="\n") as config:
        config.write("\n".join(lines) + "\n")
    print("Created .env.local-review with existing provider keys and a generated database password.")


if __name__ == "__main__":
    main()

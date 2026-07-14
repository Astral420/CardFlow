"""One-off helper to create/update the two known users.

Usage (from the backend/ directory):
    python scripts/seed_users.py "Alice" admin
    python scripts/seed_users.py "Bob" reviewer
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal  # noqa: E402
from app.models import User, UserRole  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/seed_users.py <name> <admin|reviewer>")
        raise SystemExit(1)

    name, role_str = sys.argv[1], sys.argv[2]
    role = UserRole(role_str)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.name == name).first()
        if user is None:
            user = User(name=name, role=role)
            db.add(user)
            print(f"Created user '{name}' ({role.value})")
        else:
            user.role = role
            print(f"Updated user '{name}' -> {role.value}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()

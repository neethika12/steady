"""Block until PostgreSQL accepts connections (or give up after a minute)."""

import sys
import time

from sqlalchemy import create_engine, text

from app.config import get_config


def main() -> int:
    engine = create_engine(get_config().database_url)
    deadline = time.monotonic() + 60
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database is ready.")
            return 0
        except Exception as exc:  # noqa: BLE001 - any failure means "not ready yet"
            if time.monotonic() > deadline:
                print(f"Database did not become ready: {type(exc).__name__}", file=sys.stderr)
                return 1
            time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())

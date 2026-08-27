"""Re-dispatch durable batch deletions that have been queued too long.

Usage from the backend directory:
    python -m app.commands.retry_stuck_deletions
    python -m app.commands.retry_stuck_deletions --batch-id 42
"""

import argparse

from app.tasks.deletion import enqueue_stuck_deletions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", type=int, default=None)
    parser.add_argument("--min-age-minutes", type=int, default=5)
    args = parser.parse_args()
    if args.min_age_minutes < 0:
        parser.error("--min-age-minutes must be non-negative")

    dispatched, failed = enqueue_stuck_deletions(
        min_age_minutes=args.min_age_minutes,
        batch_id=args.batch_id,
    )
    print(f"dispatched={dispatched} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

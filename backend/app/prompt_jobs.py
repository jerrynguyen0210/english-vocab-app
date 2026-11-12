"""Operator commands for inspecting prompt jobs and retrying terminal failures."""

import argparse
import json
import uuid

from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.services.prompt_jobs.management import queue_status, retry_failed_job


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "status", help="Print counts and up to 20 failed job identifiers"
    )
    retry = commands.add_parser(
        "retry", help="Reset a failed job after fixing its cause"
    )
    retry.add_argument("--word-id", required=True, type=uuid.UUID)
    args = parser.parse_args()
    engine = get_engine()
    try:
        with Session(engine) as db:
            if args.command == "status":
                print(json.dumps(queue_status(db), default=str))
            else:
                try:
                    retry_failed_job(db, args.word_id)
                except LookupError as error:
                    parser.exit(1, f"{error}\n")
                print("Failed prompt job queued for retry.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

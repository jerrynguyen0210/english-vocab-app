"""CI: migrations present in the base commit are immutable; only additions pass."""

import os
import subprocess
import sys


def check_history(base: str) -> None:
    if not base or set(base) == {"0"}:
        return  # First push has no previous tree.
    changes = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-status",
            "--no-renames",
            base,
            "HEAD",
            "--",
            "backend/migrations/versions/",
        ],
        text=True,
    ).splitlines()
    invalid = [line for line in changes if not line.startswith("A\t")]
    if invalid:
        raise SystemExit(
            "Existing migration files are immutable; add a new revision:\n"
            + "\n".join(invalid)
        )


if __name__ == "__main__":
    check_history(
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MIGRATION_BASE", "")
    )

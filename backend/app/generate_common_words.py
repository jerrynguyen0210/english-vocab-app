"""Operator-only command to generate new Common vocabulary with the configured LLM."""

import argparse

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_engine
from app.services.common_word_bank import BankGenerationStopped, populate_bank


def positive_count(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Enter a positive whole number") from None
    if number < 1:
        raise argparse.ArgumentTypeError("Enter a positive whole number")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=positive_count,
        help="Number of NEW words to add; prompts when omitted",
    )
    parser.add_argument(
        "--batch-size", type=int, choices=range(1, 21), default=20, metavar="1-20"
    )
    args = parser.parse_args()
    if args.count is None:
        try:
            args.count = positive_count(
                input("Number of new Common words to generate: ").strip()
            )
        except (EOFError, KeyboardInterrupt):
            parser.exit(1, "Generation cancelled; no words generated.\n")
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
    engine = None
    try:
        settings = get_settings()
        engine = get_engine()
        populate_bank(
            engine,
            args.count,
            settings,
            batch_size=args.batch_size,
            progress=lambda saved, total: print(
                f"Saved {saved}/{total} new Common words.", flush=True
            ),
        )
    except BankGenerationStopped as error:
        parser.exit(
            1,
            f"{error}\nCompleted batches were kept. Retry with --count {error.requested - error.inserted}.\n",
        )
    except ValueError:
        parser.exit(
            1,
            "Invalid backend configuration. Check DATABASE_URL, SECRET_KEY and private OPENROUTER settings.\n",
        )
    except SQLAlchemyError:
        parser.exit(
            1,
            "Database unavailable. Check backend database configuration and apply migrations before retrying.\n",
        )
    except KeyboardInterrupt:
        parser.exit(
            130,
            "Generation interrupted. Completed batches remain saved; check the bank before choosing a new count.\n",
        )
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()

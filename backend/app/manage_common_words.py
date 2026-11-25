"""Interactive backend menu for inspecting and managing the shared Common word bank."""

import argparse

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.database import get_engine
from app.llm.openrouter_review import ReviewError
from app.services.common_word_bank import BankGenerationStopped, populate_bank
from app.services.common_word_management import (
    BankEntry,
    BankInspection,
    all_word_ids,
    bank_summary,
    browse_words,
    delete_bank_words,
    find_word,
    inspect_bank,
    latest_words,
)
from app.services.common_word_repair import repair_bank

MENU = """
Common word database
  1. Show bank counts
  2. View latest 10 words
  3. Browse / search words
  4. View word details
  5. Generate new words with LLM
  6. Delete one word
  7. Clear the Common word bank
  8. Inspect words for duplicates and missing values
  0. Exit
"""


def show_words(words: list[BankEntry]) -> None:
    if not words:
        print("No Common words found.")
        return
    for word in words:
        print(
            f"\n{word.word} ({word.part_of_speech})\n  ID: {word.id}\n  Meaning: {word.meaning}\n  Created: {word.created_at.isoformat()}"
        )


def show_details(word: BankEntry) -> None:
    show_words([word])
    print(
        f"  Example: {word.example or 'Not provided'}\n  IPA: {word.ipa or 'Not provided'}"
    )


def positive_integer(
    prompt: str, default: int | None = None, maximum: int | None = None
) -> int:
    raw = input(prompt).strip()
    if not raw and default is not None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("Enter a positive whole number") from None
    if value < 1 or (maximum is not None and value > maximum):
        raise ValueError(
            f"Enter a number from 1 to {maximum}"
            if maximum
            else "Enter a positive whole number"
        )
    return value


def show_inspection(report: BankInspection) -> None:
    print(f"Inspected {report.words} Common words (read only).")
    print("Duplicate counts are groups; other counts are affected rows.")
    print("Example sentences and IPA are optional database fields.")
    if not report.counts:
        print("No duplicates, missing values, or normalization issues found.")
    for category, count in report.counts.items():
        print(f"\n{category}: {count}")
        for sample in report.samples[category]:
            print(f"  {sample}")
        if count > len(report.samples[category]):
            print("  Additional findings omitted; showing first 10.")


def run_menu(engine: Engine, settings: Settings) -> None:
    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()
        try:
            if choice == "0":
                return
            if choice == "1":
                counts = bank_summary(engine)
                print(
                    f"Common words: {counts['words']}\nPractice questions: {counts['questions']}\nUser progress records: {counts['progress']}\nLearned user/word pairs: {counts['learned']}"
                )
            elif choice == "2":
                show_words(latest_words(engine))
            elif choice == "3":
                search = input("Search word text (Enter to browse all): ").strip()
                cursor = None
                while True:
                    words, cursor = browse_words(engine, search, cursor)
                    show_words(words)
                    if (
                        cursor is None
                        or input("Next page? [y/N]: ").strip().casefold() != "y"
                    ):
                        break
            elif choice == "4":
                word = find_word(engine, input("Word or UUID: "))
                if word is None:
                    print("Common word not found.")
                else:
                    show_details(word)
            elif choice == "5":
                count = positive_integer("Number of NEW words to generate: ")
                batch_size = positive_integer(
                    "Words per LLM batch [20]: ", default=20, maximum=20
                )
                populate_bank(
                    engine,
                    count,
                    settings,
                    batch_size=batch_size,
                    progress=lambda saved, total: print(
                        f"Saved {saved}/{total} new Common words.", flush=True
                    ),
                )
            elif choice == "8":
                report = inspect_bank(engine)
                show_inspection(report)
                if report.counts:
                    print(
                        "LLM repair fills missing or invalid vocabulary fields, including IPA. "
                        "Duplicates, word identity, normalization and timestamps need manual review."
                    )
                    if input(
                        "Repair affected content with the LLM? [y/N]: "
                    ).strip().casefold() in {"y", "yes"}:
                        try:
                            repaired = repair_bank(
                                engine,
                                settings,
                                progress=lambda saved, total: print(
                                    f"Repaired {saved}/{total} Common words.",
                                    flush=True,
                                ),
                            )
                            print(f"Saved repairs for {repaired} Common words.")
                        except (ReviewError, ValueError):
                            print(
                                "LLM repair failed or returned invalid content. Check private "
                                "OPENROUTER settings and retry option 8. Completed repair batches remain saved."
                            )
                        except SQLAlchemyError:
                            print(
                                "Repair database operation failed. Completed batches remain saved; retry option 8."
                            )
                        print(
                            "Inspection after repair; any remaining findings need retry or manual review:"
                        )
                        show_inspection(inspect_bank(engine))
                    else:
                        print("Repair cancelled. No changes made.")
            elif choice in {"6", "7"}:
                if choice == "6":
                    word = find_word(engine, input("Word or UUID to delete: "))
                    if word is None:
                        print("Common word not found.")
                        continue
                    show_details(word)
                    ids = [word.id]
                    confirmation = f"DELETE {word.word}"
                else:
                    ids = all_word_ids(engine)
                    if not ids:
                        print("The Common bank is already empty.")
                        continue
                    print(f"Selected {len(ids)} Common words for deletion.")
                    confirmation = f"DELETE ALL {len(ids)}"
                print(
                    "This also deletes Common practice questions and user learning progress for the selected words. Saved recall words are kept."
                )
                if (
                    input(
                        f'Type "{confirmation}" to confirm, or Enter to cancel: '
                    ).strip()
                    != confirmation
                ):
                    print("Deletion cancelled.")
                    continue
                result = delete_bank_words(engine, ids)
                print(
                    f"Deleted {result.words} Common words, {result.questions} questions and {result.progress} progress records."
                )
            else:
                print("Unknown option. Choose 0-8.")
        except BankGenerationStopped as error:
            print(
                f"{error}\nCompleted batches remain saved. Choose Generate and enter the remaining count to retry."
            )
        except SQLAlchemyError:
            print(
                "Database operation failed. Check configuration and apply migrations with python -m app.migrate. Uncommitted changes were rolled back."
            )
        except ValueError:
            print(
                "Invalid input or generation configuration. Use positive whole numbers; batch size must be 1-20. Generation requires private OPENROUTER settings."
            )


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    engine = None
    try:
        settings = get_settings()
        engine = get_engine()
        run_menu(engine, settings)
    except ValueError:
        raise SystemExit(
            "Invalid backend configuration. Check DATABASE_URL, SECRET_KEY and private OPENROUTER settings."
        ) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Database unavailable. Check backend database configuration and apply migrations before retrying."
        ) from None
    except (EOFError, KeyboardInterrupt):
        print("\nMenu closed. Any completed generation batches remain saved.")
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()

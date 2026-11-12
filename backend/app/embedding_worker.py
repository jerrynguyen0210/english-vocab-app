"""Index saved words automatically; --once drains the existing backfill and exits."""

import argparse
import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_engine
from app.services.embeddings import index_batch
from app.services.errors import TopicSearchUnavailable

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    try:
        while True:
            try:
                count = index_batch(engine)
                if count:
                    logger.info("Indexed %s words", count)
                elif args.once:
                    return
                else:
                    time.sleep(5)
            except (SQLAlchemyError, TopicSearchUnavailable):
                if args.once:
                    raise SystemExit(
                        "Embedding backfill failed; check the database and embedding model."
                    ) from None
                logger.warning("Embedding indexing unavailable; retrying in 10 seconds")
                time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

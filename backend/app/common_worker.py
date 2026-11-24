"""Run the durable Common practice generation queue."""

import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_engine
from app.services.common_batches import process_one

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    try:
        while True:
            try:
                if not process_one(engine):
                    time.sleep(1)
            except SQLAlchemyError:
                logger.error(
                    "Common worker database unavailable; retrying in 5 seconds"
                )
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

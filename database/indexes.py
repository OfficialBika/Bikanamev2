import logging

logger = logging.getLogger(__name__)


async def ensure_indexes(db, settings):
    """
    Read-only mode:
    Do not create, modify, or drop MongoDB indexes.
    Existing database/collections are left untouched.
    """
    logger.info("Mongo indexes skipped: read-only mode enabled")
    return
